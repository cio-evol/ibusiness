{
    'name': 'Sales Catalog Dashboard',
    'version': '1.0',
    'summary': 'Product Dashboard with Catalog View & Financial Analytics',
    'description': """
        Dashboard module extending Product Template to provide:
        - Sales Catalog Mode (Kanban/Grid View)
        - Financial Overview (Revenue, Cost, Profit)
        - Smart Buttons linking to Sales, Invoices, Repairs, etc.
    """,
    'category': 'Sales',
    'author': 'Antigravity',
    'depends': [
        'sale', 
        'purchase', 
        'account', 
        'repair', 
        'documents', 
        'maintenance', 
        'calendar',
        'stock',
        'sale_renting',
        'project',
        'helpdesk',
    ],
    'assets': {
        'web.assets_backend': [
             'sales_catalog_dashboard/static/src/js/dashboard_graph.js',
             'sales_catalog_dashboard/static/src/js/rental_reporting_widget.js',
             'sales_catalog_dashboard/static/src/css/dashboard_ribbon.css',
             'sales_catalog_dashboard/static/src/css/rental_reporting_widget.css',
             'sales_catalog_dashboard/static/src/xml/rental_reporting_widget.xml',
        ],
    },
    'data': [
        'security/ir.model.access.csv',
        'views/product_category_views.xml',
        'views/dashboard_views.xml',
        'views/rental_reporting_views.xml',
        'views/rental_reporting_enhanced_views.xml',
        'views/asset_allocation_views.xml',
        'views/asset_allocation_add_qty_wizard_views.xml',
        'views/parking_allocation_views.xml',
        'views/parking_allocation_add_qty_wizard_views.xml',
        'views/product_schedule_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/sale_order_catalog_wizard_views.xml',
        'views/stock_lot_views.xml',
        'views/product_views.xml',
        'views/menu_items.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
