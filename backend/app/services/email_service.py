"""
Simple Email Service - Works with existing PO workflow and routes
"""
import asyncio
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import Dict, Any, List
from app.config.settings import settings
from app.services.storage_service import storage_service
import os
import base64
from jinja2 import Environment, FileSystemLoader, Template
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.email_user = settings.SMTP_USERNAME
        self.email_password = settings.SMTP_PASSWORD
        self.company_email = settings.COMPANY_EMAIL
        self.company_name = settings.COMPANY_NAME
        self.company_phone = settings.COMPANY_PHONE
        self.company_website = settings.COMPANY_WEBSITE
        self.company_contact_name = settings.COMPANY_CONTACT_NAME
        # Setup Jinja2 environment for templates
        self.template_env = self._setup_template_environment()

    def _setup_template_environment(self):
        """Setup Jinja2 template environment - Production Ready"""
        try:
            # Use environment variable or fallback to multiple paths
            # template_paths = [
                
            #     # Production path (if deployed with templates)
            #     '/app/templates/emails',
                
            #     # Development path
            #     str(Path(__file__).parent.parent / "templates" / "emails"),
                
            #     # Alternative development paths
            #     str(Path.cwd() / "app" / "templates" / "emails"),
            #     str(Path.cwd() / "templates" / "emails"),
            # ]
            
            # # Find the first valid template directory
            # template_dir = None
            # for path in template_paths:
            #     if path and os.path.exists(path) and os.path.isdir(path):
            #         template_dir = path
            #         logger.info(f"✅ Found template directory: {template_dir}")
            #         break
            
            # if not template_dir:
            #     logger.warning(f"❌ No template directory found. Searched: {[p for p in template_paths if p]}")
            #     return None
            # Since email_service.py is in app/services/, go up to app/ then to templates/emails/
            base_dir = Path(__file__).parent.parent  # Goes from services/ to app/
            template_dir = base_dir / "templates" / "emails"
            
            if not template_dir.exists():
                logger.error(f"❌ Template directory not found: {template_dir}")
                return None
            # Verify templates exist
            required_templates = ['po_approval.html', 'po_to_vendor.html', 'po_status_notification.html']
            missing_templates = []
            
            for template_name in required_templates:
                template_path = os.path.join(template_dir, template_name)
                if not os.path.exists(template_path):
                    missing_templates.append(template_name)
            
            if missing_templates:
                logger.warning(f"⚠️ Missing templates: {missing_templates}")
                # Continue anyway - fallback will handle missing templates
            
            # Setup Jinja2 environment
            env = Environment(
                loader=FileSystemLoader(template_dir),
                autoescape=True,
                # Production optimizations
                auto_reload=False if os.getenv('ENVIRONMENT') == 'production' else True,
                cache_size=100
            )
            
            logger.info(f"✅ Template environment setup successfully at: {template_dir}")
            return env
            
        except Exception as e:
            logger.error(f"❌ Failed to setup template environment: {e}")
            return None

        
    def _render_template(self, template_name: str, template_data: dict) -> str:
        """Render email template with data"""
        try:
            if not self.template_env:
                logger.error("❌ Template environment not available")
                return self._get_fallback_html(template_data)
            
            template = self.template_env.get_template(template_name)
            html_content = template.render(**template_data)
            logger.info(f"✅ Template {template_name} rendered successfully")
            return html_content
            
        except Exception as e:
            logger.error(f"❌ Error rendering template {template_name}: {e}")
            return self._get_fallback_html(template_data)

    def _get_fallback_html(self, data: dict) -> str:
        """Simple fallback HTML if template fails"""
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>{data.get('subject', 'Email from ' + self.company_name)}</title></head>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2>{self.company_name}</h2>
            <p>This is a notification from our system.</p>
            <p>Please check the attached document for details.</p>
            <hr>
            <p style="font-size: 12px; color: #666;">
                {self.company_name} | {self.company_email}
            </p>
        </body>
        </html>
        """

    async def send_po_approval_email_with_token(
        self, 
        po_number: str, 
        vendor_name: str, 
        vendor_email: str,
        total_amount: float, 
        pdf_path: str,
        order_numbers: List[str],
        approver_name: str,
        approver_email: str,
        approval_token: str
    ) -> Dict[str, Any]:
        """
        Send approval email to finance manager with:
        1. PO details in email body
        2. PDF attached to email
        3. Links for approve/reject that work with your existing routes
        """
        
        try:
            subject = f"URGENT: PO Approval Required - {po_number} (${total_amount:,.2f})"
            
            # Create links that work with your existing routes
            # The approver_email is already known (it's the recipient)
            # We'll use the finance manager's ID from your system
            
            # Links to your frontend pages that will call your existing API routes
            approve_link = f"{settings.API_BASE_URL}/po/approval/{approval_token}/approve-direct?approver_email={approver_email}"
            reject_link = f"{settings.API_BASE_URL}/po/approval/{approval_token}/reject-direct?approver_email={approver_email}"

            # Prepare template data
            template_data = {
                "company_name": self.company_name,
                "approver_name": approver_name,
                "po_number": po_number,
                "vendor_name": vendor_name,
                "vendor_email": vendor_email,
                "total_amount": f"{total_amount:,.2f}",
                "order_numbers": ", ".join(order_numbers) if isinstance(order_numbers, list) else str(order_numbers),
                "threshold": f"{settings.PO_APPROVAL_THRESHOLD:,.0f}",
                "approve_link": approve_link,
                "reject_link": reject_link,
                "approval_token": approval_token[:8],
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "help_email": self.company_email,
                "subject": subject,
            }
            # Render template
            html_body = self._render_template("po_approval.html", template_data)

            # html_body = f"""
            #     <!DOCTYPE html>
            #     <html>
            #     <head>
            #         <meta charset="UTF-8">
            #         <meta name="viewport" content="width=device-width, initial-scale=1.0">
            #         <title>PO Approval Required - {po_number}</title>
            #         <style>
            #             @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            #             * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            #             body {{ font-family: 'Inter', Arial, sans-serif; background: #f8fafc; }}
            #             .container {{ max-width: 650px; margin: 0 auto; background: white; }}
            #             .shadow {{ box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25); }}
            #         </style>
            #     </head>
            #     <body>
            #         <div class="container shadow">
                        
            #             <!-- Professional Header -->
            #             <div style="background: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #60a5fa 100%); padding: 40px 30px; position: relative; overflow: hidden;">
            #                 <div style="position: absolute; top: -50px; right: -50px; width: 120px; height: 120px; background: rgba(255,255,255,0.1); border-radius: 50%; opacity: 0.7;"></div>
            #                 <div style="position: relative; z-index: 2;">
            #                     <h1 style="color: white; font-size: 28px; font-weight: 700; margin-bottom: 8px; letter-spacing: -0.5px;">{self.company_name}</h1>
            #                     <p style="color: rgba(255,255,255,0.9); font-size: 16px; font-weight: 500;">Purchase Order Approval System</p>
            #                 </div>
            #             </div>

            #             <!-- Urgent Alert Banner -->
            #             <div style="background: linear-gradient(90deg, #fbbf24 0%, #f59e0b 100%); padding: 20px 30px; border-left: 6px solid #d97706;">
            #                 <div style="display: flex; align-items: center; gap: 12px;">
            #                     <div style="background: rgba(0,0,0,0.1); border-radius: 50%; width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;">
            #                         <span style="font-size: 20px;">⚡</span>
            #                     </div>
            #                     <div>
            #                         <h2 style="color: #92400e; font-size: 20px; font-weight: 600; margin-bottom: 4px;">Urgent Approval Required</h2>
            #                         <p style="color: #b45309; font-size: 14px; font-weight: 500;">High-value PO exceeds ${settings.PO_APPROVAL_THRESHOLD:,.0f} threshold</p>
            #                     </div>
            #                 </div>
            #             </div>

            #             <!-- Main Content -->
            #             <div style="padding: 40px 30px;">
                            
            #                 <!-- Greeting -->
            #                 <div style="margin-bottom: 32px;">
            #                     <h3 style="color: #111827; font-size: 22px; font-weight: 600; margin-bottom: 8px;">Hello {approver_name},</h3>
            #                     <p style="color: #6b7280; font-size: 16px; line-height: 1.6;">A high-value purchase order requires your immediate approval. Please review the details below and take action.</p>
            #                 </div>

            #                 <!-- PO Details Card -->
            #                 <div style="background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%); border: 1px solid #e5e7eb; border-radius: 16px; padding: 28px; margin-bottom: 32px;">
            #                     <h4 style="color: #111827; font-size: 18px; font-weight: 600; margin-bottom: 20px; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; display: inline-block;">📋 Purchase Order Details</h4>
                                
            #                     <div style="display: grid; gap: 16px;">
            #                         <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 500;">PO Number</span>
            #                             <span style="color: #1f2937; font-weight: 600; font-family: monospace; background: #eff6ff; padding: 4px 12px; border-radius: 6px;">{po_number}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 500;">Vendor</span>
            #                             <span style="color: #1f2937; font-weight: 600;">{vendor_name}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 500;">Total Amount</span>
            #                             <span style="color: #dc2626; font-weight: 700; font-size: 20px;">${total_amount:,.2f}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; padding: 12px 0;">
            #                             <span style="color: #6b7280; font-weight: 500;">Related Orders</span>
            #                             <span style="color: #1f2937; font-weight: 600; background: #f3f4f6; padding: 4px 8px; border-radius: 4px;">{order_numbers}</span>
            #                         </div>
            #                     </div>
            #                 </div>

            #                 <!-- Action Buttons -->
            #                 <div style="text-align: center; margin: 40px 0;">
            #                     <h4 style="color: #111827; font-size: 18px; font-weight: 600; margin-bottom: 24px;">Take Action</h4>
                                
            #                     <div style="display: flex; gap: 16px; justify-content: center; flex-wrap: wrap;">
            #                         <a href="{approve_link}" style="background: linear-gradient(135deg, #10b981 0%, #059669 100%); color: white; padding: 16px 32px; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 10px 25px rgba(16, 185, 129, 0.3); transition: all 0.3s ease; display: inline-block; min-width: 180px;">
            #                             ✅ APPROVE PO
            #                         </a>
            #                         <a href="{reject_link}" style="background: linear-gradient(135deg, #ef4444 0%, #dc2626 100%); color: white; padding: 16px 32px; text-decoration: none; border-radius: 12px; font-weight: 600; font-size: 16px; box-shadow: 0 10px 25px rgba(239, 68, 68, 0.3); transition: all 0.3s ease; display: inline-block; min-width: 180px;">
            #                             ❌ REJECT PO
            #                         </a>
            #                     </div>
                                
            #                     <p style="color: #6b7280; font-size: 14px; margin-top: 16px;">📎 Complete PO document is attached to this email</p>
            #                 </div>

            #                 <!-- Security Notice -->
            #                 <div style="background: #fef3c7; border: 1px solid #fbbf24; border-radius: 12px; padding: 20px; margin-top: 32px;">
            #                     <h5 style="color: #92400e; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            #                         🔒 Security Information
            #                     </h5>
            #                     <ul style="color: #b45309; font-size: 14px; line-height: 1.6; margin: 0; padding-left: 20px;">
            #                         <li>These links are personalized and expire in 48 hours</li>
            #                         <li>Only you can use these links - do not share with others</li>
            #                         <li>All actions are logged and auditable</li>
            #                     </ul>
            #                 </div>

            #             </div>

            #             <!-- Professional Footer -->
            #             <div style="background: #1f2937; padding: 32px 30px; color: #d1d5db;">
            #                 <div style="text-align: center; border-top: 1px solid #374151; padding-top: 20px;">
            #                     <p style="font-size: 14px; margin-bottom: 8px;">
            #                         <strong style="color: white;">{self.company_name}</strong> Procurement System
            #                     </p>
            #                     <p style="font-size: 12px; color: #9ca3af;">
            #                         Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Secure Token: {approval_token[:8]}...
            #                     </p>
            #                     <p style="font-size: 12px; color: #9ca3af; margin-top: 16px;">
            #                         Need help? Contact: {self.company_email}
            #                     </p>
            #                 </div>
            #             </div>

            #         </div>
            #     </body>
            #     </html>
            #     """

            
            # Download PDF from storage for email attachment
            pdf_content = await storage_service.download_po_pdf(pdf_path)
            
            result = await self._send_email_with_attachment(
                to_email=approver_email,
                subject=subject,
                html_body=html_body,
                attachment_content=pdf_content,
                attachment_name=f"{po_number}.pdf"
            )
            
            if result["success"]:
                logger.info(f"Approval email with PO PDF attachment sent to {approver_email} for PO {po_number}")
            
            return result
                
        except Exception as e:
            logger.error(f"Error sending approval email: {e}")
            return {"success": False, "error": str(e)}

    async def send_po_to_vendor(self, po_number: str, vendor_email: str, pdf_path: str) -> Dict[str, Any]:
        """Send approved PO to vendor with PDF attached"""
        
        try:
            # Get PO details from database
            from app.database.connection import db
            async with db.pool.acquire() as connection:
                po_details = await connection.fetchrow("""
                    SELECT po_number, vendor_name, total_amount, order_date
                    FROM purchase_orders WHERE po_number = $1
                """, po_number)
            
            if not po_details:
                return {"success": False, "error": "PO not found"}
            
            subject = f"📋 Purchase Order {po_details['po_number']} - {self.company_name}"
            template_data = {
                "company_name": self.company_name,
                "vendor_name": po_details['vendor_name'],
                "po_number": po_details['po_number'],
                "total_amount": f"{po_details['total_amount']:,.2f}",
                "order_date": po_details['order_date'].strftime('%B %d, %Y') if po_details['order_date'] else 'N/A',
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "help_email": self.company_email,
                "company_phone": self.company_phone,
                "company_website": self.company_website,
                "company_contact_name": self.company_contact_name,
                "subject": subject,
            }
            # Render template
            html_body = self._render_template("po_to_vendor.html", template_data)

            # html_body = f"""
            #     <!DOCTYPE html>
            #     <html>
            #     <head>
            #         <meta charset="UTF-8">
            #         <meta name="viewport" content="width=device-width, initial-scale=1.0">
            #         <title>Purchase Order - {po_details['po_number']}</title>
            #         <style>
            #             @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            #             * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            #             body {{ font-family: 'Inter', Arial, sans-serif; background: #f8fafc; }}
            #         </style>
            #     </head>
            #     <body>
            #         <div style="max-width: 650px; margin: 0 auto; background: white; box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);">
                        
            #             <!-- Header -->
            #             <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #334155 100%); padding: 40px 30px; position: relative;">
            #                 <div style="position: absolute; top: -30px; right: -30px; width: 100px; height: 100px; background: rgba(255,255,255,0.05); border-radius: 50%;"></div>
            #                 <div style="position: relative; z-index: 2;">
            #                     <h1 style="color: white; font-size: 28px; font-weight: 700; margin-bottom: 8px;">{self.company_name}</h1>
            #                     <p style="color: rgba(255,255,255,0.8); font-size: 16px;">Purchase Order Confirmation</p>
            #                 </div>
            #             </div>

            #             <!-- Main Content -->
            #             <div style="padding: 40px 30px;">
                            
            #                 <div style="margin-bottom: 32px;">
            #                     <h3 style="color: #111827; font-size: 20px; font-weight: 600; margin-bottom: 8px;">Dear {po_details['vendor_name']},</h3>
            #                     <p style="color: #6b7280; font-size: 16px; line-height: 1.6;">We are pleased to send you the approved Purchase Order <strong>{po_details['po_number']}</strong> with a total value of <strong>${po_details['total_amount']:,.2f}</strong>.</p>
            #                 </div>

            #                 <!-- Order Summary -->
            #                 <div style="background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%); border: 1px solid #3b82f6; border-radius: 16px; padding: 28px; margin-bottom: 32px;">
            #                     <h4 style="color: #1e40af; font-size: 18px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
            #                         📋 Order Summary
            #                     </h4>
            #                     <div style="background: white; border-radius: 12px; padding: 24px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);">
            #                         <div style="display: grid; gap: 16px;">
            #                             <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
            #                                 <span style="color: #6b7280; font-weight: 500;">PO Number</span>
            #                                 <span style="color: #1f2937; font-weight: 700; font-family: monospace; background: #f3f4f6; padding: 6px 12px; border-radius: 6px;">{po_details['po_number']}</span>
            #                             </div>
            #                             <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #e5e7eb;">
            #                                 <span style="color: #6b7280; font-weight: 500;">Order Date</span>
            #                                 <span style="color: #1f2937; font-weight: 600;">{po_details['order_date']}</span>
            #                             </div>
            #                             <div style="display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 2px solid #3b82f6;">
            #                                 <span style="color: #6b7280; font-weight: 500;">Total Amount</span>
            #                                 <span style="color: #059669; font-weight: 700; font-size: 24px;">${po_details['total_amount']:,.2f}</span>
            #                             </div>
            #                             <div style="display: flex; justify-content: space-between; padding: 12px 0;">
            #                                 <span style="color: #6b7280; font-weight: 500;">Status</span>
            #                                 <span style="background: #dcfce7; color: #166534; padding: 6px 16px; border-radius: 20px; font-weight: 600;">APPROVED & CONFIRMED</span>
            #                             </div>
            #                         </div>
            #                     </div>
            #                 </div>

            #                 <!-- Next Steps -->
            #                 <div style="background: #f0f9ff; border: 1px solid #0ea5e9; border-radius: 16px; padding: 28px; margin-bottom: 32px;">
            #                     <h4 style="color: #0c4a6e; font-size: 18px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; gap: 8px;">
            #                         Next Steps
            #                     </h4>
            #                     <div style="background: white; border-radius: 12px; padding: 24px;">
            #                         <ol style="color: #0c4a6e; font-size: 15px; line-height: 1.8; counter-reset: step-counter; list-style: none; padding: 0;">
            #                             <li style="counter-increment: step-counter; margin-bottom: 16px; padding-left: 40px; position: relative;">
            #                                 <span style="position: absolute; left: 0; top: 0; background: #0ea5e9; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;" data-counter></span>
            #                                 <strong>Review:</strong> Carefully examine the attached purchase order document
            #                             </li>
            #                             <li style="counter-increment: step-counter; margin-bottom: 16px; padding-left: 40px; position: relative;">
            #                                 <span style="position: absolute; left: 0; top: 0; background: #0ea5e9; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;" data-counter></span>
            #                                 <strong>Confirm:</strong> Send order confirmation within 24 hours to {self.company_email}
            #                             </li>
            #                             <li style="counter-increment: step-counter; margin-bottom: 16px; padding-left: 40px; position: relative;">
            #                                 <span style="position: absolute; left: 0; top: 0; background: #0ea5e9; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;" data-counter></span>
            #                                 <strong>Deliver:</strong> Process and deliver as per agreed timeline
            #                             </li>
            #                             <li style="counter-increment: step-counter; padding-left: 40px; position: relative;">
            #                                 <span style="position: absolute; left: 0; top: 0; background: #0ea5e9; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600;" data-counter></span>
            #                                 <strong>Invoice:</strong> Submit invoice with PO reference after delivery
            #                             </li>
            #                         </ol>
            #                     </div>
            #                 </div>

            #                 <!-- Contact Information -->
            #                 <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 12px; padding: 24px; text-align: center;">
            #                     <h5 style="color: #111827; font-weight: 600; margin-bottom: 12px;">📞 Need Support?</h5>
            #                     <p style="color: #6b7280; font-size: 14px; line-height: 1.6;">
            #                         Contact our procurement team at <a href="mailto:{self.company_email}" style="color: #3b82f6; text-decoration: none; font-weight: 600;">{self.company_email}</a><br>
            #                         Phone: {self.company_phone}
            #                     </p>
            #                 </div>

            #             </div>

            #             <!-- Footer -->
            #             <div style="background: #1f2937; padding: 32px 30px; color: #d1d5db; text-align: center;">
            #                 <p style="font-size: 14px; margin-bottom: 8px;">
            #                     <strong style="color: white;">{self.company_name}</strong> | Procurement Department
            #                 </p>
            #                 <p style="font-size: 12px; color: #9ca3af;">
            #                     This is an automated secure message. Please do not reply to this email for urgent matters.
            #                 </p>
            #             </div>

            #         </div>

            #         <style>
            #             ol[style*="counter-reset"] li[style*="counter-increment"]:nth-child(1) span[data-counter]:before {{ content: "1"; }}
            #             ol[style*="counter-reset"] li[style*="counter-increment"]:nth-child(2) span[data-counter]:before {{ content: "2"; }}
            #             ol[style*="counter-reset"] li[style*="counter-increment"]:nth-child(3) span[data-counter]:before {{ content: "3"; }}
            #             ol[style*="counter-reset"] li[style*="counter-increment"]:nth-child(4) span[data-counter]:before {{ content: "4"; }}
            #         </style>
            #     </body>
            #     </html>
            #     """

            
            # Download PDF from storage for attachment
            pdf_content = await storage_service.download_po_pdf(pdf_path)
            
            result = await self._send_email_with_attachment(
                to_email=vendor_email,
                subject=subject,
                html_body=html_body,
                attachment_content=pdf_content,
                attachment_name=f"{po_details['po_number']}.pdf"
            )
            
            if result["success"]:
                logger.info(f"PO {po_details['po_number']} with PDF attachment sent to vendor {vendor_email}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending PO to vendor: {e}")
            return {"success": False, "error": str(e)}

    async def send_po_status_notification(
        self, 
        user_email: str, 
        po_number: str, 
        status: str, 
        vendor_name: str,
        total_amount: float,
        comment: str = None,
        pdf_path: str = None
    ) -> Dict[str, Any]:
        """Send status notification to user with PO PDF attached"""
        
        try:
            # Status configuration
            status_config = {
                "approved": {
                    "staus": "approved",
                    "subject_prefix": "✅",
                    "status_text": "APPROVED",
                    "status_icon": "✅"
                },
                "rejected": {
                    "status": "rejected",
                    "subject_prefix": "❌",
                    "status_text": "REJECTED",
                    "status_icon": "❌"
                },
                "sent_to_vendor": {
                    "status": "sent_to_vendor",
                    "subject_prefix": "📤",
                    "status_text": "SENT TO VENDOR",
                    "status_icon": "📤"
                }
            }

            config = status_config.get(status, status_config["approved"])
            subject = f"{config['subject_prefix']} PO {po_number} {config['status_text'].title()} - {vendor_name}"
            # Prepare template data
            template_data = {
                "company_name": self.company_name,
                "po_number": po_number,
                "vendor_name": vendor_name,
                "total_amount": f"{total_amount:,.2f}",
                "status": status,
                "status_text": config["status_text"],
                "status_color": config["status_color"],
                "status_icon": config["status_icon"],
                "status_message": f"PO {po_number} has been {config['status_text'].lower()}",
                "comment": comment or "",
                "has_comment": comment is not None,
                "current_date": datetime.now().strftime('%B %d, %Y at %I:%M %p'),
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "help_email": self.company_email,
                "subject": subject,
            }

            # Render template
            html_body = self._render_template("po_status_notification.html", template_data)

            # html_body = f"""
            #     <!DOCTYPE html>
            #     <html>
            #     <head>
            #         <meta charset="UTF-8">
            #         <meta name="viewport" content="width=device-width, initial-scale=1.0">
            #         <title>PO Status Update - {po_number}</title>
            #         <style>
            #             @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
            #             * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            #             body {{ font-family: 'Inter', Arial, sans-serif; background: #f8fafc; }}
            #         </style>
            #     </head>
            #     <body>
            #         <div style="max-width: 600px; margin: 0 auto; background: white; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);">
                        
            #             <!-- Dynamic Header -->
            #             <div style="background: {status_color}; padding: 40px 30px; text-align: center; position: relative; overflow: hidden;">
            #                 <div style="position: absolute; top: -60px; right: -60px; width: 150px; height: 150px; background: rgba(255,255,255,0.1); border-radius: 50%;"></div>
            #                 <div style="position: relative; z-index: 2;">
            #                     <div style="background: rgba(255,255,255,0.2); border-radius: 50%; width: 80px; height: 80px; display: flex; align-items: center; justify-content: center; margin: 0 auto 16px;">
            #                         <span style="font-size: 36px;">{status_icon}</span>
            #                     </div>
            #                     <h1 style="color: white; font-size: 24px; font-weight: 700; margin-bottom: 8px;">PO Status Update</h1>
            #                     <p style="color: rgba(255,255,255,0.9); font-size: 16px;">{status_message}</p>
            #                 </div>
            #             </div>

            #             <!-- Content -->
            #             <div style="padding: 40px 30px;">
                            
            #                 <!-- Status Card -->
            #                 <div style="background: linear-gradient(135deg, #f9fafb 0%, #f3f4f6 100%); border: 2px solid {status_color}; border-radius: 16px; padding: 28px; margin-bottom: 32px;">
            #                     <div style="display: grid; gap: 16px;">
            #                         <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 600;">PO Number</span>
            #                             <span style="color: #111827; font-weight: 700; font-family: monospace; background: white; padding: 8px 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);">{po_number}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 600;">Vendor</span>
            #                             <span style="color: #111827; font-weight: 600;">{vendor_name}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 1px solid #e5e7eb;">
            #                             <span style="color: #6b7280; font-weight: 600;">Amount</span>
            #                             <span style="color: #111827; font-weight: 700; font-size: 18px;">${total_amount:,.2f}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 0; border-bottom: 2px solid {status_color};">
            #                             <span style="color: #6b7280; font-weight: 600;">Current Status</span>
            #                             <span style="background: {status_color}; color: white; padding: 8px 20px; border-radius: 20px; font-weight: 700; font-size: 14px; text-transform: uppercase;">{status}</span>
            #                         </div>
            #                         <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 0;">
            #                             <span style="color: #6b7280; font-weight: 600;">Updated</span>
            #                             <span style="color: #111827; font-weight: 600;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</span>
            #                         </div>
            #                     </div>
            #                 </div>

            #                 {f'''
            #                 <!-- Comment Section -->
            #                 <div style="background: #fef3c7; border: 1px solid #f59e0b; border-radius: 12px; padding: 24px; margin-bottom: 32px;">
            #                     <h4 style="color: #92400e; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
            #                         💬 {'Approval Comment' if status == 'approved' else 'Rejection Reason'}
            #                     </h4>
            #                     <p style="color: #b45309; font-size: 15px; line-height: 1.6; background: white; padding: 16px; border-radius: 8px;">{comment}</p>
            #                 </div>
            #                 ''' if comment else ''}

            #                 <!-- Document Notice -->
            #                 <div style="background: #ecfdf5; border: 1px solid #10b981; border-radius: 12px; padding: 24px; text-align: center;">
            #                     <h4 style="color: #065f46; font-weight: 600; margin-bottom: 12px; display: flex; align-items: center; justify-content: center; gap: 8px;">
            #                         📎 Purchase Order Document
            #                     </h4>
            #                     <p style="color: #047857; font-size: 15px; line-height: 1.6;">The complete purchase order document is attached to this email for your records. You can also view all your POs in your dashboard.</p>
            #                 </div>

            #             </div>

            #             <!-- Footer -->
            #             <div style="background: #111827; padding: 24px 30px; color: #d1d5db; text-align: center;">
            #                 <p style="font-size: 14px; margin-bottom: 4px;">
            #                     <strong style="color: white;">{self.company_name}</strong> Procurement System
            #                 </p>
            #                 <p style="font-size: 12px; color: #9ca3af;">
            #                     Automated notification | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
            #                 </p>
            #             </div>

            #         </div>
            #     </body>
            #     </html>
            #     """

            
            # Download PDF for attachment if provided
            pdf_content = None
            if pdf_path:
                pdf_content = await storage_service.download_po_pdf(pdf_path)
            
            result = await self._send_email_with_attachment(
                to_email=user_email,
                subject=subject,
                html_body=html_body,
                attachment_content=pdf_content,
                attachment_name=f"{po_number}.pdf" if pdf_content else None
            )
            
            if result["success"]:
                logger.info(f"Status notification with PDF sent to {user_email} for PO {po_number}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending status notification: {e}")
            return {"success": False, "error": str(e)}

    async def _send_email_with_attachment(
        self, 
        to_email: str, 
        subject: str, 
        html_body: str, 
        attachment_content: bytes = None,
        attachment_name: str = None
    ) -> Dict[str, Any]:
        """Send email with optional PDF attachment"""
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_user
            msg['To'] = to_email
            msg['Subject'] = subject
            
            # Attach HTML body
            msg.attach(MIMEText(html_body, 'html'))
            
            # Attach PDF if provided
            if attachment_content and attachment_name:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(attachment_content)
                encoders.encode_base64(attachment)
                attachment.add_header(
                    'Content-Disposition',
                    f'attachment; filename= {attachment_name}'
                )
                msg.attach(attachment)
            
            # Send email
            await asyncio.to_thread(self._send_email_blocking, msg)
            
            logger.info(f"Email sent successfully to {to_email}")
            return {"success": True, "message": f"Email sent to {to_email}"}
            
        except Exception as e:
            logger.error(f"Email sending error: {e}")
            return {"success": False, "error": str(e)}

    def _send_email_blocking(self, msg):
        # server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        # server.starttls()
        # server.login(self.email_user, self.email_password)
        # server.send_message(msg)
        # server.quit()
        server = smtplib.SMTP_SSL(self.smtp_server, self.smtp_port)
        server.login(self.email_user, self.email_password)
        server.send_message(msg)
        server.quit()

# Global instance
email_service = EmailService()
