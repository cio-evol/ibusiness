# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AssetCategory(models.Model):
    _name = 'asset.category'
    _description = 'Asset Category'
    _order = 'sequence, name'
    _parent_name = 'parent_id'
    _parent_store = True
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Category Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Code',
        required=True,
        tracking=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    description = fields.Text(
        string='Description',
    )
    parent_id = fields.Many2one(
        'asset.category',
        string='Parent Category',
        index=True,
        ondelete='cascade',
    )
    parent_path = fields.Char(
        index=True,
        unaccent=False,
    )
    child_ids = fields.One2many(
        'asset.category',
        'parent_id',
        string='Child Categories',
    )
    product_ids = fields.One2many(
        'product.template',
        'asset_category_id',
        string='Assets',
    )
    asset_count = fields.Integer(
        string='Asset Count',
        compute='_compute_asset_count',
    )
    active = fields.Boolean(
        string='Active',
        default=True,
    )
    color = fields.Integer(
        string='Color Index',
    )

    # Default values for assets in this category
    default_depreciation_years = fields.Integer(
        string='Default Depreciation Years',
        default=5,
        help='Default depreciation period for assets in this category',
    )
    requires_serial = fields.Boolean(
        string='Requires Serial Number',
        default=True,
        help='If checked, assets in this category must have a serial number',
    )
    requires_maintenance = fields.Boolean(
        string='Requires Regular Maintenance',
        default=False,
        help='If checked, assets in this category require regular maintenance',
    )
    maintenance_frequency = fields.Integer(
        string='Maintenance Frequency (Days)',
        default=365,
        help='Number of days between maintenance checks',
    )

    _sql_constraints = [
        ('code_uniq', 'unique(code)', 'The code must be unique!'),
    ]

    @api.depends('product_ids')
    def _compute_asset_count(self):
        for record in self:
            record.asset_count = self.env['product.template'].search_count([
                ('asset_category_id', 'child_of', record.id),
                ('is_asset', '=', True),
            ])

    def name_get(self):
        result = []
        for record in self:
            if record.parent_id:
                name = f"{record.parent_id.name} / {record.name}"
            else:
                name = record.name
            result.append((record.id, name))
        return result

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', ('name', operator, name), ('code', operator, name)]
        return self.search(domain + args, limit=limit).name_get()
