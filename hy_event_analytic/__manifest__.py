{
    'name': 'HY Event Analytic',
    'version': '1.0',
    'summary': 'Add analytic account field to product template',
    'description': 'This module adds an analytic account field to product template for event analytics',
    'category': 'Sales',
    'author': 'Chama',
    'depends': ['product', 'account', 'sale', 'event', 'website_event', 'website', 'website_event_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/product_template_views.xml',
        'views/event_event_views.xml',
        'views/event_confirmation_templates.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}

