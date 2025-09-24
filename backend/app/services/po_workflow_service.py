"""
Purchase Order Workflow Service with Sequential Steps
"""
import asyncio
from collections import defaultdict
import json
import secrets
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from app.database.connection import db
from app.services.po_pdf_generator import create_po_pdf_safe
from app.services.email_service import email_service
from app.services.storage_service import storage_service
from app.config.settings import settings
from app.utils.po_number_generator import po_number_generator
from app.websocket.connection_manager import manager
import logging

logger = logging.getLogger(__name__)

class POWorkflowService:
    def __init__(self):
        self.approval_threshold = settings.PO_APPROVAL_THRESHOLD
        self.top_k = settings.TOP_K
        self.similarity_threshold = settings.SIMILARITY_THRESHOLD
        self.company_name = settings.COMPANY_NAME
        self.company_address = settings.COMPANY_ADDRESS 
        self.company_phone = settings.COMPANY_PHONE
        self.company_email = settings.COMPANY_EMAIL
        self.company_website = settings.COMPANY_WEBSITE
        self.company_contact_name = settings.COMPANY_CONTACT_NAME
    
    async def start_po_workflow(
        self, 
        user_id: int, 
        project_id: str, 
        order_date: str,
        trigger_query: str = None
    ) -> Dict[str, Any]:
        """Start PO generation workflow (non-blocking)"""
        
        try:
            
            # Start workflow with proper date object
            workflow_result = await db.create_workflow(
                user_id=user_id,
                project_id=project_id,
                order_date=order_date,  # Pass date object, not string
                trigger_query=trigger_query
            )
            
            if not workflow_result["success"]:
                return {"success": False, "error": workflow_result["error"]}
            
            workflow_id = workflow_result["workflow_id"]
            
            # Start background task (non-blocking)
            asyncio.create_task(self._execute_workflow_steps(
                workflow_id, user_id, project_id, order_date, trigger_query
            ))
            
            return {
                "success": True,
                "workflow_id": workflow_id,
                "message": "PO generation workflow started",
                "status": "running"
            }
            
        except Exception as e:
            logger.error(f"Failed to start PO workflow: {e}")
            return {
                "success": False,
                "error": str(e)
            }
        
    async def _execute_workflow_steps(
        self, 
        workflow_id: str, 
        user_id: int, 
        project_id: str, 
        order_date: str,
        trigger_query: str = None
    ):
        """Execute the complete PO workflow in background"""
        
        try:
            # Step 1: Check SKU shortfall
            await manager.notify_workflow_progress(project_id, workflow_id, "Step 1", "Checking SKU shortfall...")
            await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=1, 
                    status='running', 
                    results={"current_step": "Checking SKU shortfall", "step_name": "step_1"}, 
                    error=None
                )
            
            sku_result = await self._step1_check_sku_shortfall(user_id, project_id, order_date, trigger_query)
            
            if not sku_result.get("has_shortfall", False):
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=1, 
                    status='completed', 
                    results={
                        **sku_result, 
                        "step_name": "step_1_completed",
                        "message": "No SKU shortfall found"
                    }, 
                    error=None
                )
                await manager.notify_workflow_complete(project_id, workflow_id, "No SKU shortfall found. No PO needed.")
                return
            
            # Step 2: Check material shortfall
            await manager.notify_workflow_progress(project_id, workflow_id, "Step 2", "Analyzing material shortfalls for production requirements...")
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=2, 
                status='running', 
                results={
                    "current_step": "Analyzing packaging and material requirements", 
                    "step_name": "step_2",
                    "sku_shortfalls_found": len(sku_result.get("sku_shortfalls", []))
                }, 
                error=None
            )
            
            material_result = await self._step2_check_packaging_shortfall(
                user_id, project_id, order_date, sku_result["sku_shortfalls"]
            )

            if not material_result.get("has_shortfall", False):
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=2, 
                    status='completed', 
                    results={
                        **material_result, 
                        "step_name": "step_2_completed",
                        "message": "No material shortfall found"
                    }, 
                    error=None
                )
                await manager.notify_workflow_complete(project_id, workflow_id, "No material shortfall found.")
                return
            
            #  Step 3: Get procurement cost with vendor details
            await manager.notify_workflow_progress(project_id, workflow_id, "Step 3", "Getting procurement costs from vendors...")
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=3, 
                status='running', 
                results={
                    "current_step": "Calculating procurement costs and vendor options", 
                    "step_name": "step_3",
                    "materials_with_shortfall": len(material_result.get("packaging_shortfalls", []))
                }, 
                error=None
            )
            
            procurement_result = await self._step3_get_procurement_costs(
                user_id, project_id, order_date, material_result["packaging_shortfalls"]
            )
            
            if not procurement_result.get("vendor_options"):
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=3, 
                    status='failed', 
                    results={
                        "step_name": "step_3_failed",
                        "materials_checked": len(material_result.get("packaging_shortfalls", []))
                    }, 
                    error="No vendors found for packaging materials"
                )
                await manager.notify_workflow_error(project_id, workflow_id, "No vendors available for required packaging materials")
                return
            
            # Step 4: Generate POs
            await manager.notify_workflow_progress(project_id, workflow_id, "Step 4", "Generating purchase orders...")
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=4, 
                status='running', 
                results={
                    "current_step": "Creating purchase order documents", 
                    "step_name": "step_4",
                    "vendor_options_found": len(procurement_result.get("vendor_options", [])),
                    "unique_vendors": procurement_result.get("unique_vendors", 0),
                    "total_procurement_cost": procurement_result.get("total_procurement_cost", 0)
                }, 
                error=None
            )
            
            po_result = await self._step4_generate_pos_from_procurement(
                user_id, project_id, order_date, workflow_id, procurement_result["vendor_grouped"], sku_result["order_numbers"]
            )
            if not po_result.get("success", False):
                error_message = po_result.get("error", "Unknown error in PO generation")
                
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=4, 
                    status='failed',  # **MARK AS FAILED**
                    results={
                        "step_name": "step_4_failed",
                        "error_details": error_message,
                        "error_summary": po_result.get("error_summary", ""),
                        "vendor_groups_processed": len(procurement_result.get("vendor_grouped", {})),
                        "failed_vendors": po_result.get("failed_vendors", []),
                        "total_failed": po_result.get("total_failed", 0),
                        "pos_generated": 0
                    },
                    error=error_message
                )
                
                # **STOP WORKFLOW HERE - DON'T CONTINUE TO STEP 5**
                await manager.notify_workflow_error(
                    project_id, 
                    workflow_id, 
                    f"❌ PO generation failed: {error_message}"
                )
                return  # **EXIT HERE - DON'T CONTINUE**

            # Handle partial success
            elif po_result.get("failed_vendors"):
                warning_message = po_result.get("warning", f"{po_result.get('total_failed', 0)} vendors failed")
                
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=4, 
                    status='completed_with_warnings',
                    results={
                        "step_name": "step_4_partial_success",
                        "pos_generated": len(po_result.get("pos_generated", [])),
                        "failed_vendors": po_result.get("failed_vendors", []),
                        "total_failed": po_result.get("total_failed", 0),
                        "success_rate": po_result.get("success_rate", 0),
                        "warning": warning_message
                    },
                    error=None
                )
                
                await manager.notify_workflow_progress(
                    project_id, 
                    workflow_id, 
                    "step_4", 
                    f"⚠️ {warning_message}. Continuing with {len(po_result.get('pos_generated', []))} successful POs..."
                )
            # Step 5: Send emails and process approvals
            await manager.notify_workflow_progress(project_id, workflow_id, "Step 5", "Processing emails and approvals...")
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=5, 
                status='running', 
                results={
                    "current_step": "Sending emails and approval requests", 
                    "step_name": "step_5",
                    "pos_to_process": len(po_result.get("pos_generated", []))
                }, 
                error=None
            )
            if po_result.get("pos_generated"):
                email_result = await self._step5_process_emails_and_approvals(po_result["pos_generated"])
            else:
                # No POs generated - mark as failed
                await db.update_workflow(
                    workflow_id=workflow_id, 
                    step=4, 
                    status='failed',
                    results={
                        "step_name": "step_4_no_pos",
                        "error": "No purchase orders could be generated"
                    },
                    error="No purchase orders could be generated"
                )
                
                await manager.notify_workflow_error(
                    project_id, 
                    workflow_id, 
                    "❌ No purchase orders could be generated"
                )
                return
            # Complete workflow
            final_result = {
                "workflow_completed": True,
                "step_name": "workflow_completed",
                "summary": {
                    "skus_with_shortfall": len(sku_result.get("sku_shortfalls", [])),
                    "packaging_materials_with_shortfall": len(material_result.get("packaging_shortfalls", [])),
                    "pos_generated": len(po_result.get("pos_generated", [])),
                    "total_procurement_cost": po_result.get("total_procurement_value", 0),
                    "vendors_involved": len(set(po["vendor_id"] for po in po_result.get("pos_generated", []))),
                    "approval_required_count": po_result.get("approval_required_count", 0),
                    "direct_to_vendor_count": po_result.get("direct_to_vendor_count", 0)
                },
                "generated_pos": po_result.get("pos_generated", []),
                "email_notifications": email_result.get("email_summary", {}),
                "completion_time": datetime.now().isoformat()
            }
            
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=5, 
                status='completed', 
                results=final_result, 
                error=None
            )
            await manager.notify_workflow_complete(
                project_id, 
                workflow_id, 
                f"Generated {len(po_result['pos_generated'])} purchase orders successfully"
            )
            
        except Exception as e:
            logger.error(f"Workflow execution error: {e}")
            error_details = {
                "step_name": "workflow_error",
                "error_type": type(e).__name__,
                "error_details": str(e),
                "workflow_id": workflow_id,
                "project_id": project_id,
                "order_date": order_date,
                "failed_at": datetime.now().isoformat()
            }
            
            await db.update_workflow(
                workflow_id=workflow_id, 
                step=-1, 
                status='failed', 
                results=error_details, 
                error=str(e)
            )
            await manager.notify_workflow_error(project_id, workflow_id, str(e))

    async def _step1_check_sku_shortfall(self, user_id: int, project_id: str, order_date: str, trigger_query: str = None) -> Dict:
        """Step 1: Check SKU shortfall using RAG service"""
        try:
            # Build query for SKU shortfall analysis
            # if trigger_query:
            #     analysis_query = f"Based on the query '{trigger_query}', analyze SKU shortfall for order date {order_date}"
            # else:
            #     analysis_query = f"""
            #     Are there enough at-hand stock (as at_hand_stock) of SKU to fulfill order for date '{order_date}'?
            #     If the at-hand stock of SKU is not sufficient, return the additional cases of SKU to be produced (as sku_shortfall_count).
            #     Include order number (as order_number) and return sku_shortfall_count with details of each SKU shortfall.
            #     """
            query = """Are there enough at hand stock (as at_hand_stock) of SKU to fulfill order for date '{order_date}'?
                If the at hand stock (as at_hand_stock) of SKU is not sufficient, then return the additional cases i.e., required - at hand stock, of SKU to be produced (as sku_shortfall_count)
                Include order number (as order_number) and return sku_shortfall_count with details of each SKU shortfall also the order quantity (as sku_order_quantity).
                Return only rows where sku_shortfall_count > 0
                If no shortfall exists, return empty result.""".format(order_date=order_date)
            
            if trigger_query:
                analysis_query = f"""
                    Based on the user query: '{trigger_query}'
                    
                    I need to check: {query}
                    """
            else:
                analysis_query = f"""
                Step 1 of procurement workflow: {query}
                """
            from app.services.rag_sql_service import rag_sql_service

            # Get embedding and relevant context
            query_embedding = await rag_sql_service.embed_query(analysis_query)
            relevant_data = await rag_sql_service.retrieve_relevant_data(
                query_embedding, user_id, project_id, top_k=self.top_k, similarity_threshold=self.similarity_threshold
            )
            
            # Generate SQL response
            sql_result = await rag_sql_service.generate_sql_response(
                analysis_query, relevant_data, []
            )
            
            if not sql_result.get("query_result", {}).get("success"):
                return {"has_shortfall": False, "error": "Could not analyze SKU shortfall"}
            
            # Process shortfall data
            shortfall_data = sql_result["query_result"]["data"]
            return await self._process_step1_sku_shortfall_data(shortfall_data)
            # shortfall_skus = []
            # total_shortfall = 0
            
            # for row in shortfall_data:
            #     if row.get("shortfall_quantity", 0) > 0 or row.get("sku_shortfall_count", 0) > 0:
            #         shortfall_qty = row.get("shortfall_quantity", 0) or row.get("sku_shortfall_count", 0)
            #         shortfall_skus.append({
            #             "sku": row.get("sku") or row.get("matnr", ""),
            #             "description": row.get("description", ""),
            #             "required_quantity": shortfall_qty,
            #             "at_hand_stock": row.get("at_hand_stock", 0),
            #             "order_number": row.get("order_number", "")
            #         })
            #         total_shortfall += shortfall_qty
            
            # return {
            #     "has_shortfall": total_shortfall > 0,
            #     "total_shortfall_count": total_shortfall,
            #     "shortfall_details": shortfall_skus,
            #     "sql_executed": sql_result.get("sql_query"),
            # }
            
        except Exception as e:
            logger.error(f"Step 1 error: {e}")
            return {"has_shortfall": False, "error": str(e)}
        
    async def _process_step1_sku_shortfall_data(self, shortfall_data: List[Dict]) -> Dict:
        """Process Step 1 SKU shortfall data following exact workflow requirements"""
        
        try:
            sku_shortfalls = []
            order_numbers = set()
            
            for row in shortfall_data:
                # Extract fields with various possible column names
                order_no = (row.get("order_number") or row.get("order_no") or 
                           row.get("orderno") or row.get("order_id") or "UNKNOWN")
                
                sku = (row.get("sku") or row.get("matnr") or row.get("material_id") or "UNKNOWN")
                order_qty = (row.get("order_quantity") or row.get("order_qty") or 0)
                required_qty = (row.get("required_quantity") or row.get("required_qty") or row.get("order_quantity") or row.get("order_qty") or 0)
                at_hand = (row.get("at_hand_stock") or row.get("stock_quantity") or 0)
                
                sku_shortfall_count = (row.get("sku_shortfall_count") or 
                                      row.get("shortfall_quantity") or 
                                      max(0, required_qty - at_hand))
                
                # Only include if sku_shortfall_count > 0 
                if sku_shortfall_count > 0:
                    sku_shortfalls.append({
                        "order_number": order_no,
                        "sku": sku,
                        "sku_order_quantity": order_qty,
                        "required_quantity": required_qty,
                        "at_hand_stock": at_hand,
                        "sku_shortfall_count": sku_shortfall_count  
                    })
                    order_numbers.add(order_no)
            
            return {
                "has_shortfall": len(sku_shortfalls) > 0,
                "sku_shortfalls": sku_shortfalls,
                "order_numbers": list(order_numbers),
                "total_skus_with_shortfall": len(sku_shortfalls),
                "step1_sql_executed": True
            }
            
        except Exception as e:
            logger.error(f"Error processing Step 1 SKU shortfall data: {e}")
            return {"has_shortfall": False, "error": str(e)}
        
    def _build_sku_shortfall_summary(self, sku_shortfalls: List[Dict]) -> str:
        """Build summary of SKU shortfalls for Step 2"""
        summary_lines = []
        for sku_data in sku_shortfalls:
            summary_lines.append(
                f"- Order {sku_data['order_number']}: SKU {sku_data['sku']}"
                f" to fulfill order quantity {sku_data['sku_order_quantity']} cases needs {sku_data['sku_shortfall_count']} additional cases"
            )
        return "\n".join(summary_lines)
    
    async def _step2_check_packaging_shortfall(self, user_id: int, project_id: str, order_date: str, sku_shortfalls: List[Dict]) -> Dict:
        """
        Step 2: To fulfill sku_order_quantity, we fall short of sku_shortfall_count cases to fulfill order for date '<date>', 
        can we check how much is the shortfall of packaging materials required, by comparing with at hand?
        Return the shortfall of packaging materials required as field packagingMaterial_shortfall_count.
        Filter by packaging material only.
        Return rows where packagingMaterial_shortfall_count > 0.
        """
        
        try:
            sku_shortfall_summary = self._build_sku_shortfall_summary(sku_shortfalls)
            analysis_query = f"""
            Step 2 of procurement workflow:
            
            SKUs with shortfalls and order quantity:
            {sku_shortfall_summary}
            To fulfill order for date '{order_date}', check how much is the shortfall of packaging materials required, by comparing with at hand stock?

            I need to:
            1. Determine packaging materials required for these SKU shortfalls
            2. Compare required packaging materials with at hand stock
            3. Calculate shortfall of packaging materials as packagingMaterial_shortfall_count
            4. Filter by packaging material only
            5. Return rows where packagingMaterial_shortfall_count > 0
            
            Return format:
            - matnr (packaging material identifier)
            - matdesc (material description)
            - material_category (e.g., packaging_material)
            - required_quantity (needed for SKU production)
            - at_hand_stock (current available stock)
            - packagingMaterial_shortfall_count (required - at hand, only if > 0)
            - werks (plant)
            - lgort (storage location)
            - used_for_skus (which SKUs this material is needed for)
            
            Filter by packaging material only.
            Return rows where packagingMaterial_shortfall_count > 0.
            """

            # analysis_query = f"""
            # As we fall short of {total_sku_shortfall} cases to fulfill order for date '{order_date}',
            # check the shortfall of packaging materials required, by comparing with at hand stock.
            # Return the shortfall of packaging materials (as packagingMaterial_shortfall_count).
            # Filter by material category 'packaging material' or 'Packaging Material' only.
            # Include material ID, description, and shortfall quantity for each packaging material.
            # """
            from app.services.rag_sql_service import rag_sql_service
            # Get embedding and relevant context
            query_embedding = await rag_sql_service.embed_query(analysis_query)
            relevant_data = await rag_sql_service.retrieve_relevant_data(
                query_embedding, user_id, project_id, top_k=self.top_k, similarity_threshold=self.similarity_threshold
            )
            
            # Generate SQL response
            sql_result = await rag_sql_service.generate_sql_response(
                analysis_query, relevant_data, []
            )
            
            if not sql_result.get("query_result", {}).get("success"):
                return {"has_shortfall": False, "error": "Could not analyze packaging material shortfall"}
            
            # Process packaging material shortfall data
            packaging_data = sql_result["query_result"]["data"]
            return await self._process_step2_packaging_shortfall_data(packaging_data)
            
            # shortfall_data = sql_result["query_result"]["data"]
            # shortfall_materials = []
            # total_shortfall = 0
            
            # for row in shortfall_data:
            #     if row.get("shortfall_quantity", 0) > 0 or row.get("packagingmaterial_shortfall_count", 0) > 0:
            #         shortfall_qty = row.get("shortfall_quantity", 0) or row.get("packagingmaterial_shortfall_count", 0)
            #         shortfall_materials.append({
            #             "material_id": row.get("material_id") or row.get("matnr", ""),
            #             "material_desc": row.get("material_desc") or row.get("description", ""),
            #             "material_category": "packaging_material",
            #             "shortfall_quantity": shortfall_qty,
            #             "werks": row.get("werks", ""),
            #             "lgort": row.get("lgort", "")
            #         })
            #         total_shortfall += shortfall_qty
            
            # return {
            #     "has_shortfall": total_shortfall > 0,
            #     "total_shortfall_count": total_shortfall,
            #     "shortfall_materials": shortfall_materials,
            #     "sql_executed": sql_result.get("sql_query")
            # }
            
        except Exception as e:
            logger.error(f"Step 2 error: {e}")
            return {"has_shortfall": False, "error": str(e)}
        
    async def _process_step2_packaging_shortfall_data(self, packaging_data: List[Dict]) -> Dict:
        """Process Step 2 packaging material shortfall data"""
        
        try:
            packaging_shortfalls = []

            for row in packaging_data:
                material_id = (row.get("material_id") or row.get("matnr") or "UNKNOWN")
                material_desc = (row.get("material_description") or row.get("matdesc") or "")
                material_cat = (row.get("material_category") or row.get("matcat") or "")

                required_qty = (row.get("required_quantity") or 0)
                at_hand = (row.get("at_hand_stock") or row.get("stock_quantity") or 0)

                # packagingMaterial_shortfall_count is the alias for packaging material shortfall
                packaging_shortfall_count = (row.get("packagingmaterial_shortfall_count") or
                                           row.get("shortfall_quantity") or
                                           max(0, required_qty - at_hand))

                werks = row.get("werks", "")
                lgort = row.get("lgort", "")
                used_for_skus = row.get("used_for_skus", "")

                # Only include if packagingMaterial_shortfall_count > 0 and is packaging material
                if (packaging_shortfall_count > 0 and
                    "packaging" in material_cat.lower()):

                    packaging_shortfalls.append({
                        "material_id": material_id,
                        "material_description": material_desc,
                        "material_category": material_cat,
                        "required_quantity": required_qty,
                        "at_hand_stock": at_hand,
                        "packagingMaterial_shortfall_count": packaging_shortfall_count,  # Exact field name
                        "werks": werks,
                        "lgort": lgort,
                        "used_for_skus": used_for_skus
                    })

            return {
                "has_shortfall": len(packaging_shortfalls) > 0,
                "packaging_shortfalls": packaging_shortfalls,
                "total_packaging_materials_with_shortfall": len(packaging_shortfalls),
                "step2_sql_executed": True
            }

        except Exception as e:
            logger.error(f"Error processing Step 2 packaging shortfall data: {e}")
            return {"has_shortfall": False, "error": str(e)}
        
    def _build_packaging_shortfall_summary(self, packaging_shortfalls: List[Dict]) -> str:
        """Build summary of packaging material shortfalls for Step 3"""
        summary_lines = []
        for material in packaging_shortfalls:
            summary_lines.append(
                f"- Material: {material['material_id']} ({material['material_description']}) ({material['material_category']}) "
                f"shortfall: {material['packagingMaterial_shortfall_count']} units "
                f"at {material['werks']}/{material['lgort']} "
                f"for SKUs {material['used_for_skus']}"
            )
        return "\n".join(summary_lines)
    
    async def _step3_get_procurement_costs(self, user_id: int, project_id: str, order_date: str, packaging_shortfalls: List[Dict]) -> Dict:
        """
        Step 3: OK now that we have identified packaging material shortfall units to fulfill order for date '<date>', 
        give me the procurement cost based on least price from vendors. Include vendor email id and order number.
        """
        
        try:
            # Build exact workflow step 3 query
            packaging_shortfall_summary = self._build_packaging_shortfall_summary(packaging_shortfalls)
            
            analysis_query = f"""
            Step 3 of procurement workflow:
            
            OK now that we have identified packaging material shortfall units to fulfill order for date '{order_date}', give the procurement cost based on least price and lead time from vendors. Include vendor details and order number.
            
            Packaging materials with shortfall:
            {packaging_shortfall_summary}
            
            I need to:
            1. Find vendors for each packaging material with shortfall
            2. Get procurement cost based on least price from vendors
            3. Include vendor email id
            4. Include order number (from original orders)
            
            Return format:
            - material_id
            - material_description
            - shortfall_quantity (packagingMaterial_shortfall_count)
            - vendor_id
            - vendor_name
            - vendor_email_id (vendor email)
            - cost_per_single_unit (least price)
            - total_procurement_cost (shortfall_quantity * cost_per_single_unit)
            - lead_time
            - werks
            - lgort
            - order_number (related order numbers)
            
            Select vendors with least price and least lead time for each material.
            Include vendor email id and order number as requested.
            """
            from app.services.rag_sql_service import rag_sql_service
            # Get embedding and relevant context
            query_embedding = await rag_sql_service.embed_query(analysis_query)
            relevant_data = await rag_sql_service.retrieve_relevant_data(
                query_embedding, user_id, project_id, top_k=self.top_k, similarity_threshold=self.similarity_threshold
            )
            
            # Let LLM generate and execute appropriate SQL
            sql_result = await rag_sql_service.generate_sql_response(
                analysis_query, relevant_data, []
            )
            
            if not sql_result.get("query_result", {}).get("success"):
                return {"vendor_options": [], "error": "Could not get procurement costs from vendors"}
            
            # Process vendor procurement data
            vendor_data = sql_result["query_result"]["data"]
            return await self._process_step3_procurement_costs_data(vendor_data, packaging_shortfalls)
            
        except Exception as e:
            logger.error(f"Step 3 error: {e}")
            return {"vendor_options": [], "error": str(e)}
        
    async def _process_step3_procurement_costs_data(self, vendor_data: List[Dict], packaging_shortfalls: List[Dict]) -> Dict:
        """Process Step 3 procurement costs data with vendor details"""
        
        try:
            vendor_options = []
            
            # Create lookup for packaging shortfalls
            shortfall_lookup = {material["material_id"]: material for material in packaging_shortfalls}
            
            for row in vendor_data:
                material_id = (row.get("material_id") or row.get("matnr") or "")
                
                if material_id in shortfall_lookup:
                    shortfall_material = shortfall_lookup[material_id]
                    
                    vendor_option = {
                        "material_id": material_id,
                        "material_description": shortfall_material["material_description"],
                        "material_category": shortfall_material["material_category"],
                        "shortfall_quantity": shortfall_material["packagingMaterial_shortfall_count"],
                        "vendor_id": row.get("vendor_id", ""),
                        "vendor_name": row.get("vendor_name", ""),
                        "vendor_email_id": row.get("vendor_email_id", ""),  # Exact field as per workflow
                        "cost_per_single_unit": float(row.get("cost_per_single_unit", 0)),
                        "total_procurement_cost": float(row.get("total_procurement_cost", 0) or (shortfall_material["packagingMaterial_shortfall_count"] * float(row.get("cost_per_single_unit", 0)))),
                        "lead_time": int(row.get("lead_time", 0)),
                        "werks": row.get("werks", ""),
                        "lgort": row.get("lgort", ""),
                        "order_number": row.get("order_number", "")  # Include order number as requested
                    }
                    
                    vendor_options.append(vendor_option)
            
            # Group by vendor to optimize PO generation
            vendor_grouped = defaultdict(list)
            for option in vendor_options:
                vendor_key = f"{option['vendor_id']}_{option['werks']}_{option['lgort']}"
                vendor_grouped[vendor_key].append(option)
            
            return {
                "vendor_options": vendor_options,
                "vendor_grouped": dict(vendor_grouped),
                "total_procurement_cost": sum(option["total_procurement_cost"] for option in vendor_options),
                "unique_vendors": len(vendor_grouped),
                "step3_sql_executed": True
            }
            
        except Exception as e:
            logger.error(f"Error processing Step 3 procurement costs data: {e}")
            return {"vendor_options": [], "error": str(e)}
        
    async def _step4_generate_pos_from_procurement(
        self, user_id: int, project_id: str, order_date: str, workflow_id: str, 
        vendor_groups: Dict[str, List[Dict]], order_numbers: List[str]
    ) -> Dict:
        """Step 4: Generate POs from procurement cost analysis"""
        
        try:

            pos_generated = []
            failed_vendors = []
            if isinstance(order_numbers, list):
                order_numbers = ','.join(str(x) for x in order_numbers if x is not None)
            elif order_numbers is None:
                order_numbers = ''
            else:
                order_numbers = str(order_numbers)

            logger.info(f"🔄 Step 4 starting: Processing {len(vendor_groups)} vendor groups")
            logger.info(f"📋 Order numbers to process: {order_numbers}")

            # Generate one PO per vendor group
            for vendor_key, vendor_materials in vendor_groups.items():
                try:
                    if not vendor_materials:
                        logger.warning(f"⚠️ Empty materials list for vendor group {vendor_key}")
                        failed_vendors.append({
                            "vendor_key": vendor_key,
                            "error": "No materials found for vendor group",
                            "vendor_name": "Unknown"
                        })
                        continue
                    # Get vendor info from first material (same vendor for all in group)
                    vendor_info = vendor_materials[0]
                    vendor_name = str(vendor_info.get("vendor_name", "Unknown Vendor"))
                    try:
                        # Generate unique PO number
                        po_number = await po_number_generator.generate_unique_po_number(
                            user_id=user_id,
                            project_id=project_id,
                            order_date=order_date,
                            vendor_id=vendor_info['vendor_id']
                        )
                        logger.info(f"📄 Generated PO number: {po_number}")
                    except Exception as po_error:
                        logger.error(f"❌ Failed to generate PO number for vendor {vendor_name}: {po_error}")
                        failed_vendors.append({
                            "vendor_key": vendor_key,
                            "vendor_name": vendor_name,
                            "error": f"PO number generation failed: {str(po_error)}"
                        })
                        await manager.notify_workflow_progress(
                                project_id, workflow_id, "step_4", 
                                f"⚠️ PO number generation failed for vendor {vendor_name}"
                            )
                        continue
                    try:
                        total_amount = sum(mat.get("total_procurement_cost", 0) for mat in vendor_materials if mat.get("total_procurement_cost") is not None)
                        if total_amount <= 0:
                            logger.warning(f"⚠️ Invalid total amount ({total_amount}) for vendor {vendor_name}")
                            failed_vendors.append({
                                "vendor_key": vendor_key,
                                "vendor_name": vendor_name,
                                "error": f"Invalid total amount: {total_amount}"
                            })
                            continue
                            
                    except (ValueError, TypeError) as e:
                        logger.error(f"❌ Error calculating total amount for vendor {vendor_name}: {e}")
                        failed_vendors.append({
                            "vendor_key": vendor_key,
                            "vendor_name": vendor_name,
                            "error": f"Amount calculation error: {str(e)}"
                        })
                        continue
                    # ENHANCED PDF DATA STRUCTURE
                    pdf_data = {
                        "po_number": po_number,
                        "user_id": user_id,        
                        "project_id": project_id,
                        "vendor": {
                            "vendor_id": vendor_info["vendor_id"],
                            "vendor_name": vendor_info["vendor_name"],
                            "vendor_email_id": vendor_info["vendor_email_id"],
                            "lead_time": vendor_info.get("lead_time", 0), 
                            "werks": vendor_info["werks"],
                            "lgort": vendor_info["lgort"]
                        },
                        "materials": [
                            {
                                "material": {
                                    "matnr": mat["material_id"],
                                    "matdesc": mat["material_description"],
                                    "matcat": mat["material_category"],
                                    "shortfall_qty": mat["shortfall_quantity"],
                                    "unit": mat.get("unit_of_measure", "EA")  # Default to Each
                                },
                                "vendor": {
                                    "cost_per_single_unit": mat["cost_per_single_unit"],
                                    "vendor_id": mat["vendor_id"],
                                    "lead_time": mat.get("lead_time", 0)
                                },
                                "total_cost": mat["total_procurement_cost"]
                            }
                            for mat in vendor_materials
                        ],
                        "total_amount": total_amount,
                        "order_date": order_date,
                        "order_numbers": order_numbers,
                        "workflow_id": workflow_id,
                        "generated_at": datetime.now().isoformat(),
                        
                        # Additional fields for enhanced PDF
                        "tax": 0.0,  # Add tax if applicable
                        "shipping": 0.0,  # Add shipping if applicable  
                        "other_charges": 0.0,  # Add other charges if applicable
                        "comments": f"Purchase order for packaging materials shortfall. Please deliver as per agreed timeline and specifications and ensure all items are properly packaged for shipping.",
                        
                        # Company details - these will be used by PDF generator
                        "company_details": {
                            "name": settings.COMPANY_NAME,
                            "address": settings.COMPANY_ADDRESS,
                            "phone": settings.COMPANY_PHONE,
                            "email": settings.COMPANY_EMAIL,
                            "website": settings.COMPANY_WEBSITE,
                            "contact_name": settings.COMPANY_CONTACT_NAME
                        }
                    }
                    
                    try:
                        pdf_result = await create_po_pdf_safe(pdf_data)
                    
                        if not pdf_result.get("success", False):
                            error_msg = pdf_result.get("error", "PDF generation failed")
                            
                            # Check for specific font/Unicode errors
                            if any(keyword in error_msg.lower() for keyword in ['font', 'unicode', 'character', 'helvetica']):
                                user_friendly_error = "PDF generation failed due to font/character issues. Using fallback format."
                                logger.error(f"❌ Font/Unicode error for vendor {vendor_name}: {error_msg}")
                            else:
                                user_friendly_error = f"PDF generation failed: {error_msg}"
                            
                            failed_vendors.append({
                                "vendor_key": vendor_key,
                                "vendor_name": vendor_name,
                                "error": user_friendly_error,
                                "error_type": "pdf_generation"
                            })
                            
                            # Immediate user notification
                            await manager.notify_workflow_progress(
                                project_id, workflow_id, "step_4", 
                                f"⚠️ PDF generation failed for vendor {vendor_name}: {user_friendly_error}"
                            )
                            continue
                        
                        logger.info(f"📄 Generated PDF: {pdf_result.get('filename', 'unknown')}")
                        
                    except Exception as pdf_error:
                        error_msg = str(pdf_error)
                        if any(keyword in error_msg.lower() for keyword in ['font', 'unicode', 'character', 'helvetica']):
                            user_friendly_error = "PDF generation failed due to font/character encoding issues"
                        else:
                            user_friendly_error = f"PDF generation error: {error_msg}"
                        
                        logger.error(f"❌ PDF generation failed for vendor {vendor_name}: {pdf_error}")
                        failed_vendors.append({
                            "vendor_key": vendor_key,
                            "vendor_name": vendor_name,
                            "error": user_friendly_error,
                            "error_type": "pdf_generation"
                        })
                        
                        # Immediate user notification
                        await manager.notify_workflow_progress(
                            project_id, workflow_id, "step_4", 
                            f"⚠️ PDF error for vendor {vendor_name}: {user_friendly_error}"
                        )
                        continue
                    
                    # Store PO record (existing code with minor fixes)
                    try:
                            order_date_obj = datetime.strptime(order_date, '%Y-%m-%d').date()
                            # Store PO record with enhanced data
                            po_data = {
                                "po_number": po_number,
                                "workflow_id": workflow_id,
                                "project_id": project_id,
                                "user_id": user_id,
                                "vendor_id": vendor_info["vendor_id"],
                                "vendor_name": vendor_info["vendor_name"],
                                "vendor_email": vendor_info["vendor_email_id"],
                                "total_amount": total_amount,
                                "status": "generated",  # Initial status
                                "needs_approval": total_amount > self.approval_threshold,
                                "order_date": order_date_obj,
                                "pdf_path": pdf_result["pdf_path"],  # From enhanced generator
                                "created_at": datetime.now(),
                                "updated_at": datetime.now()
                            }
                            
                            po_id = await db.insert_po(po_data)
                            
                            if po_id:
                                # Insert PO items with enhanced structure
                                po_items = []
                                for material in vendor_materials:
                                    po_items.append({
                                        "po_number": po_number,
                                        "matnr": material["material_id"],
                                        "matdesc": material["material_description"],
                                        "matcat": material["material_category"],
                                        "quantity": material["shortfall_quantity"],
                                        "unit_cost": material["cost_per_single_unit"],
                                        "total_cost": material["total_procurement_cost"],
                                        "vendor_id": material["vendor_id"],
                                        "order_number": order_numbers,
                                        "shortfall_reason": f"Packaging material shortfall for orders: {', '.join(order_numbers)}"
                                    })
                                try:
                                    await db.insert_po_items(po_number, po_items)

                                    # **ENHANCED PO GENERATED DATA**
                                    pos_generated.append({
                                        "po_number": po_number,
                                        "vendor_id": vendor_info["vendor_id"],
                                        "vendor_name": vendor_info["vendor_name"],
                                        "vendor_email": vendor_info["vendor_email_id"],
                                        "total_amount": total_amount,
                                        "needs_approval": total_amount > self.approval_threshold,
                                        "pdf_path": pdf_result["pdf_path"],
                                        "pdf_filename": pdf_result["filename"],
                                        "materials_count": len(vendor_materials),
                                        "order_numbers": order_numbers,
                                        "generated_at": datetime.now().isoformat(),
                                        "approval_threshold": self.approval_threshold,
                                        "status": "generated"
                                    })
                                
                                    logger.info(f"✅ Generated corporate PO: {po_number} for vendor {vendor_info['vendor_name']} with total amount ${total_amount:,.2f}")

                                except Exception as po_items_error:
                                    logger.error(f"❌ PO items insertion failed for {po_number}: {po_items_error}")
                                    
                                    cleanup_success = await storage_service.cleanup_failed_po_pdf(pdf_result, po_number)
            
                                    # Also try to delete the PO record that was created
                                    try:
                                        await db.delete_po(po_number)
                                        logger.info(f"🧹 Cleaned up PO record: {po_number}")
                                    except Exception as po_delete_error:
                                        logger.error(f"❌ Failed to cleanup PO record {po_number}: {po_delete_error}")

                                    failed_vendors.append({
                                        "vendor_key": vendor_key,
                                        "vendor_name": vendor_name,
                                        "error": str(po_items_error),
                                        "error_type": "database_po_items",
                                        "cleanup_performed": cleanup_success
                                    })
                                    continue
                                # Log PO generation details
                                # await db.log_po_event(po_number, "po_generated", {
                                #     "vendor_name": vendor_info["vendor_name"],
                                #     "total_amount": total_amount,
                                #     "materials_count": len(vendor_materials),
                                #     "order_numbers": order_numbers,
                                #     "pdf_generated": True
                                # })
                            else:
                                # **PO INSERTION FAILED - CLEANUP PDF**
                                logger.error(f"❌ PO insertion failed for vendor {vendor_name}")
                                
                                # Cleanup the uploaded PDF
                                cleanup_success = await storage_service.cleanup_failed_po_pdf(pdf_result, po_number)
                                
                                # Add to failed vendors
                                failed_vendors.append({
                                    "vendor_key": vendor_key,
                                    "vendor_name": vendor_name,
                                    "error": f"PO database insertion failed. PDF cleaned up.",
                                    "error_type": "database_po",
                                    "cleanup_performed": cleanup_success
                                })
                                continue 
                                                
                    except Exception as db_error:
                        error_msg = f"Database storage failed: {str(db_error)}"
                        logger.error(f"❌ Database insertion failed for vendor {vendor_name}: {db_error}")
                        cleanup_success = await storage_service.cleanup_failed_po_pdf(pdf_result, po_number)
    
                        failed_vendors.append({
                            "vendor_key": vendor_key,
                            "vendor_name": vendor_name,
                            "error": f"{error_msg}. PDF cleaned up.",
                            "error_type": "database",
                            "cleanup_performed": cleanup_success
                        })
                        continue
                
                except Exception as vendor_error:
                    error_msg = f"Critical processing error: {str(vendor_error)}"
                    logger.error(f"❌ Critical error processing vendor group {vendor_key}: {vendor_error}")
                    failed_vendors.append({
                        "vendor_key": vendor_key,
                        "vendor_name": vendor_name if 'vendor_name' in locals() else "Unknown",
                        "error": error_msg,
                        "error_type": "critical"
                    })
                    continue
            
            total_successful = len(pos_generated)
            total_failed = len(failed_vendors)
            total_attempted = total_successful + total_failed

            # Log summary
            logger.info(f"📊 Step 4 Summary: {total_successful}/{total_attempted} POs generated successfully")

            if failed_vendors:
                logger.warning(f"⚠️ Failed vendor groups ({total_failed}):")
                for failed in failed_vendors:
                    logger.warning(f"  - {failed['vendor_name']} ({failed['vendor_key']}): {failed['error']}")

            # **CRITICAL FIX: Determine success based on actual results**
            if total_successful == 0 and total_failed > 0:
                # COMPLETE FAILURE
                error_summary = self._create_error_summary(failed_vendors)
                
                await manager.notify_workflow_error(
                    project_id, workflow_id, 
                    f"❌ All {total_failed} vendors failed. {error_summary}"
                )
                
                return {
                    "success": False,  # **CHANGED: Mark as failed**
                    "error": f"All {total_failed} vendor groups failed to generate POs",
                    "error_summary": error_summary,
                    "failed_vendors": failed_vendors,
                    "pos_generated": [],
                    "total_pos": 0,
                    "total_failed": total_failed,
                    "total_procurement_value": 0,
                    "approval_required_count": 0,
                    "direct_to_vendor_count": 0
                }
                
            elif total_failed > 0:
                # PARTIAL SUCCESS
                error_summary = self._create_error_summary(failed_vendors)
                
                await manager.notify_workflow_progress(
                    project_id, workflow_id, "step_4",
                    f"⚠️ Generated {total_successful} POs successfully. {total_failed} vendors failed: {error_summary}"
                )
                
                return {
                    "success": True,  # Still successful since some POs generated
                    "pos_generated": pos_generated,
                    "total_pos": total_successful,
                    "total_procurement_value": sum(po["total_amount"] for po in pos_generated),
                    "approval_required_count": sum(1 for po in pos_generated if po["needs_approval"]),
                    "direct_to_vendor_count": sum(1 for po in pos_generated if not po["needs_approval"]),
                    "failed_vendors": failed_vendors,
                    "total_failed": total_failed,
                    "warning": f"{total_failed} out of {total_attempted} vendor groups failed",
                    "success_rate": (total_successful / total_attempted * 100) if total_attempted > 0 else 0
                }

            else:
                # COMPLETE SUCCESS
                return {
                    "success": True,
                    "pos_generated": pos_generated,
                    "total_pos": total_successful,
                    "total_procurement_value": sum(po["total_amount"] for po in pos_generated),
                    "approval_required_count": sum(1 for po in pos_generated if po["needs_approval"]),
                    "direct_to_vendor_count": sum(1 for po in pos_generated if not po["needs_approval"]),
                    "failed_vendors": [],
                    "total_failed": 0
                }
            
        except Exception as e:
            logger.error(f"Step 4 error: {e}")
            return {"success": False, "error": str(e)}
        
    def _create_error_summary(self, failed_vendors: List[Dict]) -> str:
        """Create user-friendly error summary"""
        if not failed_vendors:
            return ""
        
        error_counts = {}
        for vendor in failed_vendors:
            error_type = vendor.get("error_type", "unknown")
            if error_type not in error_counts:
                error_counts[error_type] = 0
            error_counts[error_type] += 1
        
        summary_parts = []
        for error_type, count in error_counts.items():
            if error_type == "pdf_generation":
                summary_parts.append(f"PDF issues({count})")
            elif error_type == "database":
                summary_parts.append(f"Database errors({count})")
            else:
                summary_parts.append(f"{error_type}({count})")
        
        return "; ".join(summary_parts)
    
    async def _step5_process_emails_and_approvals(self, pos_generated: List[Dict]):
        """Step 5: Process emails and approvals"""
        
        try:
            email_results = {
                "approval_emails_sent": 0,
                "vendor_emails_sent": 0,
                "direct_vendor_sends": 0,
                "approval_requests_created": 0,
                "errors": [],
                "failed_pos": [],
                "processed_pos": [],
            }
            for po in pos_generated:
                po_number = po["po_number"]
                try:
                    if po["needs_approval"]:
                        approval_result = await self._send_approval_email(po)
                    
                        if approval_result.get("success", True):  # Default to True if no explicit result
                            email_results["approval_emails_sent"] += 1
                            email_results["approval_requests_created"] += 1
                            email_results["processed_pos"].append({
                                "po_number": po_number,
                                "action": "sent_for_approval",
                                "recipient": approval_result.get("approver_email", "finance_manager"),
                                "amount": po["total_amount"]
                            })
                            logger.info(f"✅ Approval request sent for PO {po_number}")
                        else:
                            email_results["errors"].append(f"Approval email failed for {po_number}: {approval_result.get('error', 'Unknown error')}")
                            email_results["failed_pos"].append(po_number)
                            
                    else:
                        # Send directly to vendor
                        vendor_result = await self._send_po_to_vendor(po)
                        
                        if vendor_result.get("success", True):  # Default to True if no explicit result
                            email_results["direct_vendor_sends"] += 1
                            email_results["vendor_emails_sent"] += 1
                            email_results["processed_pos"].append({
                                "po_number": po_number,
                                "action": "sent_to_vendor",
                                "recipient": po["vendor_email"],
                                "vendor": po["vendor_name"],
                                "amount": po["total_amount"]
                            })
                            logger.info(f"✅ PO {po_number} sent directly to vendor {po['vendor_name']}")
                        else:
                            email_results["errors"].append(f"Vendor email failed for {po_number}: {vendor_result.get('error', 'Unknown error')}")
                            email_results["failed_pos"].append(po_number)
                            
                except Exception as e:
                    error_msg = f"Error processing {po_number}: {str(e)}"
                    email_results["errors"].append(error_msg)
                    email_results["failed_pos"].append(po_number)
                    logger.error(error_msg)
            
            # Calculate success metrics
            total_successful = email_results["approval_emails_sent"] + email_results["direct_vendor_sends"]
            
            return {
                "success": True,
                "email_summary": email_results,
                "total_processed": len(pos_generated),
                "successful_operations": total_successful,
                "error_count": len(email_results["errors"]),
                "success_rate": (total_successful / len(pos_generated)) * 100 if pos_generated else 100,
                "completion_time": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"❌ Step 5 critical error: {e}")
            return {
                "success": False,
                "error": str(e),
                "email_summary": {"errors": [str(e)]},
                "total_processed": len(pos_generated),
                "successful_operations": 0,
                "error_count": 1
            }
    
    # In po_workflow_service.py, update the _send_approval_email method:

    async def _send_approval_email(self, po: Dict):
        """Send secure approval request to finance manager"""
        
        try:
            # Get finance manager details
            finance_manager = await db.get_finance_manager()
            
            if finance_manager:
                # Generate secure approval token
                approval_token = secrets.token_urlsafe(32)
                token_expires_at = datetime.utcnow() + timedelta(hours=48)  # 48 hour expiry
                
                # Store approval request with token in database
                success = await db.create_approval_request_with_token(
                    po_number=po["po_number"],
                    approver_email=finance_manager["emp_email_id"], 
                    approval_token=approval_token,
                    token_expires_at=token_expires_at
                )
                
                if not success:
                    error_msg = f"Failed to create approval request with token for PO {po['po_number']}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                
                # Send email with token-based approval links
                result = await email_service.send_po_approval_email_with_token(
                    po_number=po["po_number"],
                    vendor_name=po["vendor_name"],
                    vendor_email=po["vendor_email"],
                    total_amount=po["total_amount"],
                    pdf_path=po["pdf_path"],
                    order_numbers=po["order_numbers"],
                    approver_name=finance_manager["emp_name"],
                    approver_email=finance_manager["emp_email_id"],
                    approval_token=approval_token
                )
                
                if result["success"]:
                    # Update status
                    await db.update_po_status(po["po_number"], "pending_approval")
                    logger.info(f"Secure approval email sent for PO {po['po_number']} to {finance_manager['emp_email_id']}")
                    return {
                        "success": True,
                        "approver_email": finance_manager["emp_email_id"],
                        "approver_name": finance_manager["emp_name"],
                        "token_expires_at": token_expires_at.isoformat(),
                        "po_status": "pending_approval"
                    }
                else:
                    error_msg = f"Failed to send approval email for PO {po['po_number']}: {result.get('error', 'Email service error')}"
                    logger.error(error_msg)
                    return {"success": False, "error": error_msg}
                    
            else:
                error_msg = "No finance manager found in staff directory"
                logger.error(error_msg)
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Exception in approval email process for PO {po['po_number']}: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}

    
    async def _send_po_to_vendor(self, po: Dict):
        """Send PO directly to vendor"""
        
        try:
            vendor_result = await email_service.send_po_to_vendor(
                po_number=po["po_number"],
                vendor_email=po["vendor_email"],
                pdf_path=po["pdf_path"]
            )
            
            if vendor_result["success"]:
                # Update PO status to sent to vendor
                await db.update_po_status(
                    po["po_number"], 
                    "sent_to_vendor", 
                    f"Sent directly to vendor {po['vendor_name']} - no approval required"
                )
                
                logger.info(f"✅ PO {po['po_number']} sent directly to vendor {po['vendor_name']} ({po['vendor_email']})")
                
                return {
                    "success": True,
                    "vendor_email": po["vendor_email"],
                    "vendor_name": po["vendor_name"],
                    "po_status": "sent_to_vendor",
                    "sent_at": datetime.now().isoformat()
                }
            else:
                error_msg = f"Failed to send PO to vendor {po['vendor_name']}: {vendor_result.get('error', 'Email service error')}"
                logger.error(error_msg)
                
                # Update PO status to failed
                await db.update_po_status(po["po_number"], "failed", f"Failed to send to vendor: {vendor_result.get('error')}")
                
                return {"success": False, "error": error_msg}
                
        except Exception as e:
            error_msg = f"Exception sending PO {po['po_number']} to vendor {po.get('vendor_name', 'Unknown')}: {str(e)}"
            logger.error(error_msg)
            
            # Update PO status to failed
            try:
                await db.update_po_status(po["po_number"], "failed", f"Exception occurred: {str(e)}")
            except:
                pass  # Don't fail if status update fails
                
            return {"success": False, "error": error_msg}
    
    async def get_user_pos(self, user_id: int, project_id: str) -> List[Dict]:
        """Get all POs for a user/project"""
        
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                pos = await connection.fetch("""
                    SELECT po_number, vendor_name, total_amount, status, needs_approval,
                           pdf_path, created_at::text, updated_at::text
                    FROM purchase_orders 
                    WHERE user_id = $1 AND project_id = $2
                    ORDER BY created_at DESC
                """, user_id, project_id)
                
                return [dict(po) for po in pos]
                
        except Exception as e:
            logger.error(f"Error fetching user POs: {e}")
            return []

    async def approve_po_with_token(self, token: str, approver_email: str, comment: str = None) -> Dict[str, Any]:
        """Approve PO using secure token"""
        try:
            # Validate token and get details
            approval_details = await db.validate_approval_token(token)
            if not approval_details:
                return {"success": False, "error": "Invalid or expired approval token"}
            
            # Verify approver email matches
            if approver_email.lower() != approval_details["approver_email"].lower():
                return {"success": False, "error": "Unauthorized approver"}
            
            # Process approval
            result = await db.process_approval_decision(
                token=token,
                decision="approved", 
                approver_email=approver_email,
                comment=comment
            )
            
            if result["success"]:
                po_number = result["po_number"]
                await manager.broadcast_to_project(
                    approval_details["project_id"],
                    {
                        "type": "po_status_update", 
                        "po_number": po_number,
                        "status": "approved",  
                        "message": f"PO {po_number} has been approved",
                        "timestamp": datetime.now().isoformat()
                    }
                )
                
                # Continue with vendor notification (same as existing approve_po method)
                async with db.pool.acquire() as connection:
                    po_details = await connection.fetchrow("""
                        SELECT po_number, vendor_email, pdf_path, user_id, project_id, vendor_name, total_amount
                        FROM purchase_orders 
                        WHERE po_number = $1
                    """, po_number)
                    
                    if po_details:
                        # Send to vendor and notify user (same logic as existing method)
                        vendor_result = await email_service.send_po_to_vendor(
                            po_number=po_details['po_number'],
                            vendor_email=po_details['vendor_email'], 
                            pdf_path=po_details['pdf_path']
                        )
                        
                        if vendor_result["success"]:
                            await db.update_po_status(po_number, "sent_to_vendor")
                            
                            # WebSocket notification
                            await manager.notify_po_status_update(
                                project_id=po_details['project_id'],
                                po_number=po_number,
                                status="sent_to_vendor",
                                message=f"PO {po_number} approved by {approver_email}"
                            )
                            
                return {
                    "success": True,
                    "status": "sent_to_vendor", 
                    "po_number": po_number,
                    "approved_by": approver_email
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Token approval error: {e}")
            return {"success": False, "error": str(e)}

    async def reject_po_with_token(self, token: str, approver_email: str, reason: str) -> Dict[str, Any]:
        """Reject PO using secure token"""
        try:
            # Validate token and get details  
            approval_details = await db.validate_approval_token(token)
            if not approval_details:
                return {"success": False, "error": "Invalid or expired approval token"}
            
            # Verify approver email matches
            if approver_email.lower() != approval_details["approver_email"].lower():
                return {"success": False, "error": "Unauthorized approver"}
            
            # Process rejection
            result = await db.process_approval_decision(
                token=token,
                decision="rejected",
                approver_email=approver_email,
                comment=reason
            )
            
            if result["success"]:
                po_number = result["po_number"]
                await manager.broadcast_to_project(
                    approval_details["project_id"],
                        {
                            "type": "po_status_update", 
                            "po_number": po_number,
                            "status": "rejected",  
                            "message": f"PO {po_number} has been rejected",
                            "timestamp": datetime.now().isoformat()
                        }
                )
                # Notify user about rejection via WebSocket
                async with db.pool.acquire() as connection:
                    po_details = await connection.fetchrow("""
                        SELECT project_id FROM purchase_orders WHERE po_number = $1
                    """, po_number)
                    
                    if po_details:
                        await manager.notify_po_status_update(
                            project_id=po_details['project_id'],
                            po_number=po_number,
                            status="rejected",
                            message=f"PO {po_number} rejected by {approver_email}: {reason}"
                        )
                
                return {
                    "success": True,
                    "status": "rejected",
                    "po_number": po_number, 
                    "rejected_by": approver_email,
                    "reason": reason
                }
            else:
                return result
                
        except Exception as e:
            logger.error(f"Token rejection error: {e}")
            return {"success": False, "error": str(e)}
        
    async def get_po_approval_status(self, po_number: str, user_id: int) -> Optional[Dict]:
        """Get approval status and details for a PO"""
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                approval_details = await connection.fetchrow("""
                    SELECT ar.status, ar.approver_email, ar.comment, ar.token_expires_at,
                           ar.created_at::text as requested_at, ar.updated_at::text as processed_at,
                           po.needs_approval, po.total_amount, po.status as po_status
                    FROM po_approval_requests ar
                    JOIN purchase_orders po ON ar.po_number = po.po_number
                    WHERE ar.po_number = $1 AND po.user_id = $2
                """, po_number, user_id)
                
                return dict(approval_details) if approval_details else None
                
        except Exception as e:
            logger.error(f"Error getting approval status: {e}")
            return None

    async def cancel_po_approval(self, po_number: str, user_id: int, reason: str) -> Dict[str, Any]:
        """Cancel a pending PO approval request"""
        try:
            # Verify PO belongs to user and is pending approval
            po_details = await db.get_po_details_with_items(po_number, user_id)
            if not po_details:
                return {"success": False, "error": "PO not found"}
            
            if po_details["status"] != "pending_approval":
                return {"success": False, "error": "PO is not pending approval"}
            
            # Update PO status to cancelled
            await db.update_po_status(po_number, "cancelled", f"Cancelled by user: {reason}")
            
            # Update approval request
            await db.update_approval_request(po_number, "cancelled", user_id, reason)
            
            return {
                "success": True,
                "message": f"PO {po_number} approval cancelled successfully",
                "cancelled_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error cancelling PO approval: {e}")
            return {"success": False, "error": str(e)}

    async def resend_approval_email(self, po_number: str, user_id: int) -> Dict[str, Any]:
        """Resend approval email for a PO"""
        try:
            # Verify PO belongs to user and needs approval
            po_details = await db.get_po_details_with_items(po_number, user_id)
            if not po_details:
                return {"success": False, "error": "PO not found"}
            
            if po_details["status"] != "pending_approval":
                return {"success": False, "error": "PO is not pending approval"}
            
            # Prepare PO data for email resend
            po_data = {
                "po_number": po_number,
                "vendor_name": po_details["vendor_name"],
                "vendor_email": po_details["vendor_email"],
                "total_amount": float(po_details["total_amount"]),
                "pdf_path": po_details["pdf_path"],
                "order_numbers": []  # You might want to get this from workflow data
            }
            
            # Resend approval email
            await self._send_approval_email(po_data)
            
            return {
                "success": True,
                "message": f"Approval email resent for PO {po_number}",
                "resent_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error resending approval email: {e}")
            return {"success": False, "error": str(e)}

    async def get_workflow_summary(self, user_id: int, project_id: str, days: int = 30) -> Dict[str, Any]:
        """Get workflow summary statistics"""
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                # Get workflow statistics
                since_date = datetime.now() - timedelta(days=days)
                
                workflows = await connection.fetch("""
                    SELECT status, COUNT(*) as count
                    FROM po_workflows 
                    WHERE user_id = $1 AND project_id = $2 AND created_at >= $3
                    GROUP BY status
                """, user_id, project_id, since_date)
                
                pos = await connection.fetch("""
                    SELECT status, COUNT(*) as count, SUM(total_amount) as total_amount
                    FROM purchase_orders 
                    WHERE user_id = $1 AND project_id = $2 AND created_at >= $3
                    GROUP BY status
                """, user_id, project_id, since_date)
                
                workflow_stats = {row["status"]: row["count"] for row in workflows}
                po_stats = {
                    row["status"]: {
                        "count": row["count"], 
                        "total_amount": float(row["total_amount"] or 0)
                    } 
                    for row in pos
                }
                
                return {
                    "period_days": days,
                    "workflow_statistics": workflow_stats,
                    "po_statistics": po_stats,
                    "total_workflows": sum(workflow_stats.values()),
                    "total_pos": sum(stat["count"] for stat in po_stats.values()),
                    "total_procurement_value": sum(stat["total_amount"] for stat in po_stats.values())
                }
                
        except Exception as e:
            logger.error(f"Error getting workflow summary: {e}")
            return {}

    async def validate_workflow_permissions(self, workflow_id: str, user_id: int) -> bool:
        """Validate if user has access to workflow"""
        try:
            workflow = await db.get_workflow_status(workflow_id)
            return workflow is not None and workflow.get("user_id") == user_id
        except Exception as e:
            logger.error(f"Error validating workflow permissions: {e}")
            return False

    async def get_pending_approvals_count(self, user_id: int, project_id: str) -> int:
        """Get count of POs pending approval for user"""
        try:
            async with db.pool.acquire() as connection:
                await connection.execute(f"SET LOCAL app.current_user_id = {user_id}")
                
                count = await connection.fetchval("""
                    SELECT COUNT(*)
                    FROM purchase_orders 
                    WHERE user_id = $1 AND project_id = $2 AND status = 'pending_approval'
                """, user_id, project_id)
                
                return count or 0
                
        except Exception as e:
            logger.error(f"Error getting pending approvals count: {e}")
            return 0

    async def get_workflow_progress(self, workflow_id: str, user_id: int) -> Optional[Dict]:
        """Get workflow progress details"""
        try:
            workflow_status = await db.get_workflow_status(workflow_id)
            if workflow_status:
                # Add PO information if completed
                if workflow_status.get('status') == 'completed':
                    pos = await db.get_pos_by_workflow(workflow_id, user_id)
                    workflow_status['generated_pos'] = pos
                
            return workflow_status
        except Exception as e:
            logger.error(f"Error getting workflow progress: {e}")
            return None

    async def approve_po(self, po_number: str, approver_email: str, comment: str = None) -> Dict:
        """Legacy approve PO method (non-token based)"""
        try:
            # Update PO status
            await db.update_po_status(po_number, "approved")
            
            # Update approval request (if exists)
            try:
                await db.update_approval_request(po_number, "approved", approver_email, comment)
            except Exception as e:
                logger.warning(f"No approval request to update for PO {po_number}: {e}")

            # Get PO details for vendor email
            async with db.pool.acquire() as connection:
                po_details = await connection.fetchrow("""
                    SELECT po_number, vendor_email, pdf_path, user_id, project_id, vendor_name, total_amount
                    FROM purchase_orders 
                    WHERE po_number = $1
                """, po_number)
                
                if po_details:
                    # Send PO to vendor
                    vendor_result = await email_service.send_po_to_vendor(
                        po_number=po_details['po_number'],
                        vendor_email=po_details['vendor_email'],
                        pdf_path=po_details['pdf_path']
                    )
                    
                    if vendor_result["success"]:
                        # Update status to sent_to_vendor
                        await db.update_po_status(po_number, "sent_to_vendor")
                        
                        # Notify user about approval
                        # user = await db.get_user_by_id(po_details['user_id'])
                        # if user and user.get('email'):
                        #     await email_service.send_po_status_notification(
                        #         user_email=user['email'],
                        #         po_number=po_number,
                        #         status="approved",
                        #         vendor_name=po_details['vendor_name'],
                        #         total_amount=float(po_details['total_amount']),
                        #         comment=comment
                        #     )
                        
                        # Send WebSocket notification
                        await manager.notify_po_status_update(
                            project_id=po_details['project_id'],
                            po_number=po_number,
                            status="sent_to_vendor",
                            message=f"PO {po_number} approved and sent to {po_details['vendor_name']}"
                        )
                        
                        return {
                            "success": True, 
                            "status": "sent_to_vendor",
                            "message": f"PO approved and sent to vendor {po_details['vendor_name']}"
                        }
                    else:
                        return {
                            "success": False, 
                            "error": f"PO approved but failed to send to vendor: {vendor_result.get('error')}"
                        }
                else:
                    return {"success": False, "error": "PO not found"}
                    
        except Exception as e:
            logger.error(f"Approval error: {e}")
            return {"success": False, "error": str(e)}

    async def reject_po(self, po_number: str, approver_email: str, reason: str) -> Dict:
        """Legacy reject PO method (non-token based)"""
        try:
            # Update PO status
            await db.update_po_status(po_number, "rejected", reason)
            
            # Update approval request (if exists)
            try:
                await db.update_approval_request(po_number, "rejected", approver_email, reason)
            except Exception as e:
                logger.warning(f"No approval request to update for PO {po_number}: {e}")

            # Get PO details for notifications
            async with db.pool.acquire() as connection:
                po_details = await connection.fetchrow("""
                    SELECT user_id, project_id, vendor_name, total_amount
                    FROM purchase_orders 
                    WHERE po_number = $1
                """, po_number)
                
                if po_details:
                    # Notify user about rejection
                    # user = await db.get_user_by_id(po_details['user_id'])
                    # if user and user.get('email'):
                    #     await email_service.send_po_status_notification(
                    #         user_email=user['email'],
                    #         po_number=po_number,
                    #         status="rejected",
                    #         vendor_name=po_details['vendor_name'],
                    #         total_amount=float(po_details['total_amount']),
                    #         comment=reason
                    #     )
                    
                    # WebSocket notification
                    await manager.notify_po_status_update(
                        project_id=po_details['project_id'],
                        po_number=po_number,
                        status="rejected",
                        message=f"PO {po_number} rejected by {approver_email}: {reason}"
                    )

            return {"success": True, "status": "rejected"}
            
        except Exception as e:
            logger.error(f"Rejection error: {e}")
            return {"success": False, "error": str(e)}

# Global instance
po_workflow_service = POWorkflowService()
