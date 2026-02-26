{
    "name": "Dubai Ejari Management",
    "summary": "End-to-end Ejari lifecycle management for Dubai rental properties.",
    "description": """
Dubai Ejari Management
=======================

Manage Ejari records for Dubai rental properties:

- Ejari records with lifecycle states and renewal links
- Expiry tracking and notifications
- Integration with product templates (rooms/units)
- Multi-company aware, company-specific settings
""",
    "version": "19.0.1.0.0",
    "author": "Your Company",
    "website": "https://www.yourcompany.example",
    "category": "Real Estate/Property Management",
    "license": "LGPL-3",
    "depends": ["base", "mail", "product","sales_catalog_dashboard"],
    "data": [
        "security/ejari_security.xml",
        "security/ir.model.access.csv",
        "data/sequence.xml",
        "data/cron.xml",
        "data/mail_template.xml",
        "views/ejari_record_views.xml",
        "views/product_template_views.xml",
        "views/product_dashboard_ejari_views.xml",
        "views/res_company_views.xml",
    ],
    "application": True,
    "installable": True,
}
