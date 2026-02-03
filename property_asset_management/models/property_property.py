# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class PropertyProperty(models.Model):
    _name = 'property.property'
    _description = 'Property'
    _order = 'sequence, name'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'display_name'

    name = fields.Char(
        string='Property Name',
        required=True,
        tracking=True,
    )
    code = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    display_name = fields.Char(
        string='Display Name',
        compute='_compute_display_name',
        store=True,
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )
    property_type_id = fields.Many2one(
        'property.type',
        string='Property Type',
        required=True,
        tracking=True,
        index=True,
    )
    parent_id = fields.Many2one(
        'property.property',
        string='Parent Property',
        index=True,
        ondelete='restrict',
        tracking=True,
    )
    child_ids = fields.One2many(
        'property.property',
        'parent_id',
        string='Child Properties',
    )
    child_count = fields.Integer(
        string='Child Count',
        compute='_compute_child_count',
    )

    # Location Details
    street = fields.Char(string='Street')
    street2 = fields.Char(string='Street 2')
    city = fields.Char(string='City')
    state_id = fields.Many2one(
        'res.country.state',
        string='State',
        domain="[('country_id', '=', country_id)]",
    )
    country_id = fields.Many2one(
        'res.country',
        string='Country',
    )
    zip = fields.Char(string='ZIP')

    # Property Details
    floor = fields.Char(string='Floor')
    room_number = fields.Char(string='Room Number')
    area = fields.Float(string='Area (sqm)')
    capacity = fields.Integer(string='Capacity (Persons)')

    # Contact
    responsible_id = fields.Many2one(
        'res.users',
        string='Responsible',
        tracking=True,
        default=lambda self: self.env.user,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('maintenance', 'Under Maintenance'),
        ('inactive', 'Inactive'),
    ], string='Status', default='draft', tracking=True, required=True)

    active = fields.Boolean(string='Active', default=True)

    # Assets
    asset_assignment_ids = fields.One2many(
        'asset.assignment',
        'property_id',
        string='Asset Assignments',
    )
    asset_count = fields.Integer(
        string='Asset Count',
        compute='_compute_asset_count',
    )
    total_asset_value = fields.Float(
        string='Total Asset Value',
        compute='_compute_asset_count',
    )

    # Additional Info
    description = fields.Html(string='Description')
    notes = fields.Text(string='Internal Notes')
    image = fields.Binary(string='Image', attachment=True)

    # Dates
    acquisition_date = fields.Date(string='Acquisition Date')

    _sql_constraints = [
        ('code_company_uniq', 'unique(code, company_id)',
         'The reference must be unique per company!'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', _('New')) == _('New'):
                vals['code'] = self.env['ir.sequence'].next_by_code('property.property') or _('New')
        return super().create(vals_list)

    @api.depends('name', 'code', 'parent_id')
    def _compute_display_name(self):
        for record in self:
            if record.parent_id:
                record.display_name = f"{record.parent_id.name} / {record.name} [{record.code}]"
            else:
                record.display_name = f"{record.name} [{record.code}]"

    @api.depends('child_ids')
    def _compute_child_count(self):
        for record in self:
            record.child_count = len(record.child_ids)

    @api.depends('asset_assignment_ids', 'asset_assignment_ids.state')
    def _compute_asset_count(self):
        for record in self:
            active_assignments = record.asset_assignment_ids.filtered(
                lambda a: a.state == 'assigned'
            )
            record.asset_count = len(active_assignments)
            record.total_asset_value = sum(
                active_assignments.mapped('asset_id.list_price')
            )

    @api.constrains('parent_id')
    def _check_parent_id(self):
        if not self._check_recursion():
            raise ValidationError(_('Error! You cannot create recursive properties.'))

    def action_activate(self):
        self.write({'state': 'active'})

    def action_maintenance(self):
        self.write({'state': 'maintenance'})

    def action_deactivate(self):
        self.write({'state': 'inactive'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_view_assets(self):
        self.ensure_one()
        return {
            'name': _('Assets'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.assignment',
            'view_mode': 'list,form',
            'domain': [('property_id', '=', self.id)],
            'context': {'default_property_id': self.id},
        }

    def action_view_children(self):
        self.ensure_one()
        return {
            'name': _('Child Properties'),
            'type': 'ir.actions.act_window',
            'res_model': 'property.property',
            'view_mode': 'list,form',
            'domain': [('parent_id', '=', self.id)],
            'context': {'default_parent_id': self.id},
        }

    def action_transfer_equipment(self):
        self.ensure_one()
        return {
            'name': _('Transfer Equipment'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.transfer',
            'view_mode': 'form',
            'context': {'default_source_property_id': self.id},
        }
