# -*- coding: utf-8 -*-
{
    'name': 'Property & Asset Management',
    'version': '19.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Manage Properties (Buildings, Meeting Rooms) and their Assets',
    'description': """
        Property & Asset Management Module
        ===================================
        This module extends Odoo Inventory to manage:
        - Properties: Buildings, Meeting Rooms, Offices, etc.
        - Assets: Monitors, Projectors, Furniture, Equipment, etc.
        - Asset assignment to properties
        - Asset tracking and maintenance
        - Property hierarchy (Buildings > Floors > Rooms)
    """,
    'author': 'Advaccura',
    'website': 'https://www.advaccura.com',
    'license': 'LGPL-3',
    'depends': [
        'base',
        'stock',
        'product',
        'mail',
    ],
    'data': [
        'security/property_asset_security.xml',
        'security/ir.model.access.csv',
        'data/property_asset_data.xml',
        'data/ir_sequence_data.xml',
        'views/property_views.xml',
        'views/property_type_views.xml',
        'views/product_template_views.xml',
        'views/asset_category_views.xml',
        'views/asset_assignment_views.xml',
        'views/asset_maintenance_views.xml',
        'views/asset_transfer_views.xml',
        'report/property_asset_report.xml',
        'report/property_asset_report_templates.xml',
        'views/menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'application': True,
    'auto_install': False,
    'images': ['static/description/icon.png'],
}
