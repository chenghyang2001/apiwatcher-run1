"""
PDF export functionality for incident reports.
"""

from io import BytesIO
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib import colors
from sqlalchemy.orm import Session

from .models import Incident, Endpoint, Check


def generate_incident_pdf(incident_id: int, db: Session) -> bytes:
    """
    Generate a PDF report for an incident.

    Args:
        incident_id: The incident ID to export
        db: Database session

    Returns:
        PDF file content as bytes
    """
    # Fetch incident data
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        raise ValueError(f"Incident {incident_id} not found")

    # Fetch endpoint data
    endpoint = db.query(Endpoint).filter(Endpoint.id == incident.endpoint_id).first()
    if not endpoint:
        raise ValueError(f"Endpoint {incident.endpoint_id} not found")

    # Fetch checks during incident window
    checks = (
        db.query(Check)
        .filter(Check.endpoint_id == incident.endpoint_id)
        .filter(Check.checked_at >= incident.started_at)
    )

    if incident.resolved_at:
        checks = checks.filter(Check.checked_at <= incident.resolved_at)

    checks = checks.order_by(Check.checked_at.desc()).limit(20).all()

    # Create PDF in memory
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)

    # Container for PDF elements
    story = []

    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#1f2937'),
        spaceAfter=12,
        alignment=TA_CENTER
    )
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor('#374151'),
        spaceAfter=10,
        spaceBefore=20
    )
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=11,
        textColor=colors.HexColor('#4b5563'),
        spaceAfter=8
    )

    # Title
    story.append(Paragraph("📊 APIWatcher Incident Report", title_style))
    story.append(Spacer(1, 0.2*inch))

    # Status badge
    status_text = "🔴 OPEN" if not incident.resolved_at else "🟢 RESOLVED"
    severity_color = {
        "HIGH": "#dc2626",
        "MEDIUM": "#f59e0b",
        "LOW": "#10b981"
    }.get(incident.severity, "#6b7280")

    story.append(Paragraph(
        f"<b>Status:</b> {status_text} &nbsp;&nbsp; "
        f"<b>Severity:</b> <font color='{severity_color}'>{incident.severity}</font>",
        body_style
    ))
    story.append(Spacer(1, 0.3*inch))

    # Incident metadata table
    story.append(Paragraph("Incident Details", heading_style))

    incident_data = [
        ["Incident ID", f"#{incident.id}"],
        ["Endpoint Name", endpoint.name],
        ["Endpoint URL", endpoint.url],
        ["Environment", endpoint.environment.upper()],
        ["Started At", incident.started_at.strftime("%Y-%m-%d %H:%M:%S UTC")],
        ["Resolved At", incident.resolved_at.strftime("%Y-%m-%d %H:%M:%S UTC") if incident.resolved_at else "Still open"],
        ["Duration", f"{incident.duration_mins} minutes" if incident.duration_mins else "Ongoing"],
        ["Failure Count", str(incident.failure_count)],
        ["Acknowledged", "Yes" if incident.acknowledged else "No"]
    ]

    incident_table = Table(incident_data, colWidths=[2*inch, 4.5*inch])
    incident_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f3f4f6')),
        ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#374151')),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))

    story.append(incident_table)
    story.append(Spacer(1, 0.3*inch))

    # Claude AI Report
    if incident.claude_report:
        story.append(Paragraph("🤖 AI Analysis Report", heading_style))

        # Split report into paragraphs for better formatting
        report_lines = incident.claude_report.split('\n')
        for line in report_lines:
            if line.strip():
                story.append(Paragraph(line.strip(), body_style))

        story.append(Spacer(1, 0.3*inch))

    # Check history during incident
    if checks:
        story.append(Paragraph("Check History During Incident", heading_style))

        check_data = [["Time", "Status", "Code", "Response Time", "Error"]]
        for check in checks:
            check_data.append([
                check.checked_at.strftime("%H:%M:%S"),
                "✅ Pass" if check.passed else "❌ Fail",
                str(check.status_code) if check.status_code else "N/A",
                f"{check.response_time}ms" if check.response_time else "N/A",
                (check.error_message[:30] + "...") if check.error_message else "-"
            ])

        check_table = Table(check_data, colWidths=[1.2*inch, 0.9*inch, 0.7*inch, 1.2*inch, 2.5*inch])
        check_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f2937')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1d5db')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('RIGHTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')])
        ]))

        story.append(check_table)
        story.append(Spacer(1, 0.3*inch))

    # Footer
    story.append(Spacer(1, 0.5*inch))
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#9ca3af'),
        alignment=TA_CENTER
    )
    story.append(Paragraph(
        f"Generated by APIWatcher on {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
        footer_style
    ))

    # Build PDF
    doc.build(story)

    # Get PDF bytes
    pdf_bytes = buffer.getvalue()
    buffer.close()

    return pdf_bytes
