import io
import os
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def generate_invoice_pdf(payment_data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter, 
        rightMargin=0.5*inch, leftMargin=0.5*inch, 
        topMargin=0.5*inch, bottomMargin=0.5*inch
    )
    elements = []
    styles = getSampleStyleSheet()
    
    primary_color = colors.HexColor('#8B0000')
    bg_color = colors.HexColor('#fef2f2')
    border_color = colors.HexColor('#fee2e2')
    text_gray = colors.HexColor('#475569')
    
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], textColor=primary_color, fontSize=24, spaceAfter=20)
    right_text = ParagraphStyle('RightText', parent=styles['Normal'], alignment=2, textColor=text_gray)
    
    raw_ref = payment_data.get('transaction_id', 'N/A')
    parts = raw_ref.split('-')
    if len(parts) >= 4 and raw_ref.startswith('FGCEOSA-PSTK'):
        short_ref = parts[2].upper()
    else:
        short_ref = raw_ref[:12].upper()
        
    logo_path = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.jpg")
    logo_img = ""
    if os.path.exists(logo_path):
        logo_img = Image(logo_path)
        logo_img.drawHeight = 1.0 * inch
        logo_img.drawWidth = 1.0 * inch
        logo_img.hAlign = 'LEFT'
        
    company_info = Paragraph(
        "<b>FGC Enugu Old Students Association</b><br/>"
        "Connecting Alumni. Celebrating Legacy.<br/>"
        "hello@allfgcealumni.org<br/>"
        "https://portal.allfgcealumni.org", 
        right_text
    )
    
    header_table = Table([[logo_img, company_info]], colWidths=[2.5*inch, 5*inch])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    
    elements.append(header_table)
    elements.append(Spacer(1, 0.3 * inch))
    
    elements.append(Paragraph("PAYMENT RECEIPT", title_style))
    
    billed_to = Paragraph(
        f"<b>Billed To:</b><br/>{payment_data.get('member_name', 'Member')}<br/>{payment_data.get('email', '')}",
        styles['Normal']
    )
    
    receipt_details = Paragraph(
        f"<b>Date:</b> {payment_data.get('date')}<br/>"
        f"<b>Receipt No:</b> {short_ref}",
        right_text
    )
    
    info_table = Table([[billed_to, receipt_details]], colWidths=[4*inch, 3.5*inch])
    info_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 0.4 * inch))
    
    amount = payment_data.get('amount', 0)
    items_data = [
        ["DESCRIPTION", "AMOUNT"],
        [payment_data.get('description', 'Association Dues'), f"NGN {amount:,.2f}"],
        ["", ""],
        ["TOTAL PAID", f"NGN {amount:,.2f}"]
    ]
    
    item_table = Table(items_data, colWidths=[5.5*inch, 2*inch])
    item_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), primary_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('PADDING', (0, 0), (-1, 0), 10),
        
        ('PADDING', (0, 1), (-1, 1), 15),
        ('FONTNAME', (0, 1), (0, 1), 'Helvetica'),
        ('FONTNAME', (1, 1), (1, 1), 'Helvetica-Bold'),
        
        ('LINEBELOW', (0, 1), (-1, 1), 1, border_color),
        ('BOTTOMPADDING', (0, 1), (-1, 1), 15),
        
        ('FONTNAME', (0, 3), (-1, 3), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 3), (-1, 3), bg_color),
        ('PADDING', (0, 3), (-1, 3), 12),
        
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
    ]))
    
    elements.append(item_table)
    elements.append(Spacer(1, 0.6 * inch))
    
    thank_you = Paragraph(
        "Thank you for your payment and continued support of FGCEOSA!", 
        ParagraphStyle('CenterBold', parent=styles['Normal'], alignment=1, textColor=primary_color, fontName='Helvetica-Bold')
    )
    elements.append(thank_you)
    
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
