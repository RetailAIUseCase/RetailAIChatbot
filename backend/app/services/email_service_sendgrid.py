"""
SendGrid Email Service - Simple & Professional
"""
import sendgrid
from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
import base64
from datetime import datetime
from typing import Dict, Any, List
from app.config.settings import settings
from app.services.storage_service import storage_service
import logging

logger = logging.getLogger(__name__)

class EmailService:
    def __init__(self):
        self.sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
        self.from_email = settings.SENDGRID_FROM_EMAIL
        self.company_name = settings.COMPANY_NAME
        self.company_email = settings.COMPANY_EMAIL
        self.company_phone = settings.COMPANY_PHONE
        self.company_website = settings.COMPANY_WEBSITE
        self.company_contact_name = settings.COMPANY_CONTACT_NAME

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
        """Send PO approval email using SendGrid template"""
        
        try:
            # Create approval links
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
                "help_email": self.company_email
            }
            
            # Create email
            message = Mail(
                from_email=self.from_email,
                to_emails=approver_email,
                subject=f"URGENT: PO Approval Required - {po_number} (${total_amount:,.2f})"
            )
            
            # Use SendGrid template
            message.template_id = settings.SENDGRID_PO_APPROVAL_TEMPLATE_ID
            message.dynamic_template_data = template_data
            
            # Add PDF attachment
            pdf_content = await storage_service.download_po_pdf(pdf_path)
            if pdf_content:
                encoded_pdf = base64.b64encode(pdf_content).decode()
                attachment = Attachment(
                    FileContent(encoded_pdf),
                    FileName(f"{po_number}.pdf"),
                    FileType("application/pdf"),
                    Disposition("attachment")
                )
                message.attachment = attachment
            
            # Send email
            response = self.sg.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"✅ SendGrid approval email sent to {approver_email} for PO {po_number}")
                return {
                    "success": True,
                    "message": f"Approval email sent to {approver_email}",
                    "message_id": response.headers.get('X-Message-Id')
                }
            else:
                logger.error(f"❌ SendGrid error: {response.status_code} - {response.body}")
                return {"success": False, "error": f"SendGrid error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ SendGrid approval email error: {e}")
            return {"success": False, "error": str(e)}

    async def send_po_to_vendor(self, po_number: str, vendor_email: str, pdf_path: str) -> Dict[str, Any]:
        """Send approved PO to vendor using SendGrid template"""
        
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
            
            # Prepare template data
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
                "company_contact_name": self.company_contact_name
            }
            
            # Create email
            message = Mail(
                from_email=self.from_email,
                to_emails=vendor_email,
                subject=f"Purchase Order {po_details['po_number']} - {self.company_name}"
            )
            
            # Use SendGrid template
            message.template_id = settings.SENDGRID_PO_VENDOR_TEMPLATE_ID
            message.dynamic_template_data = template_data
            
            # Add PDF attachment
            pdf_content = await storage_service.download_po_pdf(pdf_path)
            if pdf_content:
                encoded_pdf = base64.b64encode(pdf_content).decode()
                attachment = Attachment(
                    FileContent(encoded_pdf),
                    FileName(f"{po_details['po_number']}.pdf"),
                    FileType("application/pdf"),
                    Disposition("attachment")
                )
                message.attachment = attachment
            
            # Send email
            response = self.sg.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"✅ SendGrid vendor email sent to {vendor_email} for PO {po_number}")
                return {
                    "success": True,
                    "message": f"PO sent to {vendor_email}",
                    "message_id": response.headers.get('X-Message-Id')
                }
            else:
                logger.error(f"❌ SendGrid vendor error: {response.status_code}")
                return {"success": False, "error": f"SendGrid error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ SendGrid vendor email error: {e}")
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
        """Send PO status update notification using SendGrid template"""
        
        try:
            # Status configuration
            status_config = {
                "approved": {
                    "subject_prefix": "✅",
                    "status_color": "#22c55e",
                    "status_text": "APPROVED",
                    "status_icon": "✅"
                },
                "rejected": {
                    "subject_prefix": "❌",
                    "status_color": "#ef4444", 
                    "status_text": "REJECTED",
                    "status_icon": "❌"
                },
                "sent_to_vendor": {
                    "subject_prefix": "📤",
                    "status_color": "#3b82f6",
                    "status_text": "SENT TO VENDOR",
                    "status_icon": "📤"
                }
            }
            
            config = status_config.get(status, status_config["approved"])
            
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
                "help_email": self.company_email
            }
            
            # Create email
            message = Mail(
                from_email=self.from_email,
                to_emails=user_email,
                subject=f"{config['subject_prefix']} PO {po_number} {config['status_text'].title()} - {vendor_name}"
            )
            
            # Use SendGrid template
            message.template_id = settings.SENDGRID_PO_STATUS_TEMPLATE_ID
            message.dynamic_template_data = template_data
            
            # Add PDF attachment if provided
            if pdf_path:
                pdf_content = await storage_service.download_po_pdf(pdf_path)
                if pdf_content:
                    encoded_pdf = base64.b64encode(pdf_content).decode()
                    attachment = Attachment(
                        FileContent(encoded_pdf),
                        FileName(f"{po_number}.pdf"),
                        FileType("application/pdf"),
                        Disposition("attachment")
                    )
                    message.attachment = attachment
            
            # Send email
            response = self.sg.send(message)
            
            if response.status_code in [200, 202]:
                logger.info(f"✅ SendGrid status notification sent to {user_email} for PO {po_number}")
                return {
                    "success": True,
                    "message": f"Status notification sent to {user_email}",
                    "message_id": response.headers.get('X-Message-Id')
                }
            else:
                logger.error(f"❌ SendGrid status error: {response.status_code}")
                return {"success": False, "error": f"SendGrid error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ SendGrid status notification error: {e}")
            return {"success": False, "error": str(e)}

# Global instance
email_service = EmailService()
