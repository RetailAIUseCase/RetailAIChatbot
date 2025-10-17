"""
Simple Email Service - Works with existing PO workflow and routes
"""
import sendgrid
from sendgrid.helpers.mail import Mail, To, From, Attachment, FileContent, FileName, FileType, Disposition, Category
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
        self.from_email = settings.SENDGRID_FROM_EMAIL
        self.email_provider = settings.EMAIL_PROVIDER
        self.sg = None
        if self.email_provider == 'sendgrid':
            api_key = getattr(settings, 'SENDGRID_API_KEY', None)
            if api_key:
                self.sg = sendgrid.SendGridAPIClient(api_key=api_key)
                logger.info(f"✅ SendGrid client initialized")
            else:
                logger.error("❌ SENDGRID_API_KEY not found but EMAIL_PROVIDER=sendgrid")
    

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
        approval_token: str,
        approval_threshold: int
    ) -> Dict[str, Any]:
        """
        Send approval email to finance manager with:
        1. PO details in email body
        2. PDF attached to email
        3. Links for approve/reject that work with your existing routes
        """
        
        try:
            subject = f"URGENT: PO Approval Required - {po_number} (${total_amount:,.2f})"
            
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
                "threshold": f"{approval_threshold:,.0f}",
                "approve_link": approve_link,
                "reject_link": reject_link,
                "approval_token": approval_token[:8],
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "help_email": self.company_email,
                "subject": subject,
            }
            print("_________________________________________________________",template_data['threshold'])
            # Render template
            html_body = self._render_template("po_approval.html", template_data)

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
                # "status_color": config["status_color"],
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
        """Send email with optional PDF attachment via SendGrid"""
        
        try:
            # Route based on provider
            if not to_email or not isinstance(to_email, str):
                logger.error(f"❌ Invalid to_email: {to_email}")
                return {"success": False, "error": "Invalid email address"}
            
            # Route based on provider
            if self.email_provider == 'sendgrid':
                if not self.sg:
                    logger.error("❌ SendGrid client not available, falling back to SMTP")
                    return await self._send_via_smtp(
                        to_email, subject, html_body, attachment_content, attachment_name
                    )
                return await self._send_via_sendgrid(
                    to_email, subject, html_body, attachment_content, attachment_name
                )
            else:
                return await self._send_via_smtp(
                    to_email, subject, html_body, attachment_content, attachment_name
                )
                
        except Exception as e:
            logger.error(f"❌ Email sending error: {e}")
            return {"success": False, "error": str(e)}
        
    async def _send_via_sendgrid(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        attachment_content: bytes = None,
        attachment_name: str = None
    ) -> Dict[str, Any]:
        """Send email via SendGrid HTTP API"""
        
        try:
            if not self.sg:
                logger.error("❌ SendGrid client not initialized")
                return {"success": False, "error": "SendGrid client not initialized"}
            
            # Ensure to_email is a string (SendGrid Mail handles both string and list)
            to_emails = to_email if isinstance(to_email, str) else str(to_email)
            # Create Mail object
            message = Mail(
                from_email=From(self.from_email),
                to_emails=[To(to_emails)],
                subject=subject,
                html_content=html_body
            )
            
            # Add PDF attachment if provided
            if attachment_content and attachment_name:
                logger.info(f"📎 Adding attachment: {attachment_name}")
                encoded_file = base64.b64encode(attachment_content).decode()
                
                attached_file = Attachment(
                    FileContent(encoded_file),
                    FileName(attachment_name),
                    FileType('application/pdf'),
                    Disposition('attachment')
                )
                message.add_attachment(attached_file)
                logger.info(f"✅ Attachment added successfully")
            
            # Add category for tracking
            message.add_category(Category('po-workflow'))
            
            # Send via SendGrid API
            logger.info(f"🚀 Sending email...")
            logger.info(f"   From: {self.from_email}")
            logger.info(f"   To: {to_emails}")
        
            logger.info(f"🚀 Sending email via SendGrid...")
            response = await asyncio.to_thread(self.sg.send, message)
            logger.info(f"📨 SendGrid response status: {response.status_code}")
            if response.status_code == 202:
                logger.info(f"✅ SendGrid email sent successfully to {to_email}")
                return {"success": True, "message": f"Email sent to {to_email}"}
            else:
                logger.error(f"❌ SendGrid returned status {response.status_code}: {response.body}")
                return {"success": False, "error": f"SendGrid error: {response.status_code}"}
                
        except Exception as e:
            logger.error(f"❌ SendGrid send failed: {str(e)}")
            return {"success": False, "error": str(e)}
        
    async def _send_via_smtp(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        attachment_content: bytes = None,
        attachment_name: str = None
    ) -> Dict[str, Any]:
        """Send email via SMTP (fallback for local dev)"""
        
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
            
            # Send email via SMTP
            await asyncio.to_thread(self._send_email_blocking, msg)
            
            logger.info(f"✅ SMTP email sent successfully to {to_email}")
            return {"success": True, "message": f"Email sent to {to_email}"}
            
        except Exception as e:
            logger.error(f"❌ SMTP sending error: {e}")
            return {"success": False, "error": str(e)}

    def _send_email_blocking(self, msg):
        """SMTP blocking send - keep unchanged"""
        server = smtplib.SMTP(self.smtp_server, self.smtp_port)
        server.starttls()
        server.login(self.email_user, self.email_password)
        server.send_message(msg)
        server.quit()

    # async def _send_email_with_attachment(
    #     self, 
    #     to_email: str, 
    #     subject: str, 
    #     html_body: str, 
    #     attachment_content: bytes = None,
    #     attachment_name: str = None
    # ) -> Dict[str, Any]:
    #     """Send email with optional PDF attachment"""
        
    #     try:
    #         msg = MIMEMultipart()
    #         msg['From'] = self.email_user
    #         msg['To'] = to_email
    #         msg['Subject'] = subject
            
    #         # Attach HTML body
    #         msg.attach(MIMEText(html_body, 'html'))
            
    #         # Attach PDF if provided
    #         if attachment_content and attachment_name:
    #             attachment = MIMEBase('application', 'octet-stream')
    #             attachment.set_payload(attachment_content)
    #             encoders.encode_base64(attachment)
    #             attachment.add_header(
    #                 'Content-Disposition',
    #                 f'attachment; filename= {attachment_name}'
    #             )
    #             msg.attach(attachment)
            
    #         # Send email
    #         await asyncio.to_thread(self._send_email_blocking, msg)
            
    #         logger.info(f"Email sent successfully to {to_email}")
    #         return {"success": True, "message": f"Email sent to {to_email}"}
            
    #     except Exception as e:
    #         logger.error(f"Email sending error: {e}")
    #         return {"success": False, "error": str(e)}

    # def _send_email_blocking(self, msg):
    #     server = smtplib.SMTP(self.smtp_server, self.smtp_port)
    #     server.starttls()
    #     server.login(self.email_user, self.email_password)
    #     server.send_message(msg)
    #     server.quit()

# Global instance
email_service = EmailService()
