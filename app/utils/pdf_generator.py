import io
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

def generate_invoice_pdf(payment_data: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'TitleStyle', parent=styles['Heading1'],
        textColor=colors.HexColor('#8B0000'), alignment=1
    )
    
    elements.append(Paragraph("ALLFGCEOSA - Payment Receipt", title_style))
    elements.append(Spacer(1, 20))
    
    member_info = [
        ["Member Name:", payment_data.get('member_name', 'N/A')],
        ["Email:", payment_data.get('email', 'N/A')],
        ["Date:", payment_data.get('date', datetime.now().strftime('%Y-%m-%d %H:%M'))],
        ["Transaction Ref:", payment_data.get('transaction_id', 'N/A')],
    ]
    
    t1 = Table(member_info, colWidths=[120, 300])
    t1.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t1)
    elements.append(Spacer(1, 20))
    
    payment_details = [
        ["Payment Description", "Amount"],
        [payment_data.get('description', 'Association Payment'), f"NGN {payment_data.get('amount', 0):,.2f}"]
    ]
    
    t2 = Table(payment_details, colWidths=[320, 100])
    t2.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#8B0000')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 12),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#fef2f2')),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#fee2e2')),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
    ]))
    elements.append(t2)
    
    elements.append(Spacer(1, 40))
    elements.append(Paragraph("Thank you for your payment and support!", ParagraphStyle(
        'Footer', parent=styles['Normal'], alignment=1, textColor=colors.HexColor('#64748b')
    )))
    
    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
