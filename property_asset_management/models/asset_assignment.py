# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class AssetAssignment(models.Model):
    _name = 'asset.assignment'
    _description = 'Asset Assignment'
    _order = 'assignment_date desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Reference',
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _('New'),
    )
    asset_id = fields.Many2one(
        'product.template',
        string='Asset',
        required=True,
        domain=[('is_asset', '=', True)],
        tracking=True,
    )
    asset_code = fields.Char(
        related='asset_id.asset_code',
        string='Asset Code',
        store=True,
    )
    asset_category_id = fields.Many2one(
        related='asset_id.asset_category_id',
        string='Asset Category',
        store=True,
    )
    property_id = fields.Many2one(
        'property.property',
        string='Property',
        required=True,
        tracking=True,
    )
    property_type_id = fields.Many2one(
        related='property_id.property_type_id',
        string='Property Type',
        store=True,
    )
    assigned_to_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        tracking=True,
    )
    assigned_by_id = fields.Many2one(
        'res.users',
        string='Assigned By',
        default=lambda self: self.env.user,
        tracking=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Dates
    assignment_date = fields.Date(
        string='Assignment Date',
        default=fields.Date.today,
        required=True,
        tracking=True,
    )
    expected_return_date = fields.Date(
        string='Expected Return Date',
        tracking=True,
    )
    actual_return_date = fields.Date(
        string='Actual Return Date',
        tracking=True,
    )

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('returned', 'Returned'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    # Condition
    condition_on_assignment = fields.Selection([
        ('new', 'New'),
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
    ], string='Condition on Assignment', default='good')
    condition_on_return = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('damaged', 'Damaged'),
    ], string='Condition on Return')

    # Notes
    assignment_notes = fields.Text(string='Assignment Notes')
    return_notes = fields.Text(string='Return Notes')

    # Acknowledgment
    acknowledgment_required = fields.Boolean(
        string='Acknowledgment Required',
        default=True,
    )
    acknowledged = fields.Boolean(
        string='Acknowledged',
        default=False,
        tracking=True,
    )
    acknowledged_date = fields.Datetime(
        string='Acknowledged Date',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.assignment') or _('New')
        return super().create(vals_list)

    @api.constrains('asset_id', 'state')
    def _check_asset_availability(self):
        for record in self:
            if record.state == 'assigned':
                existing = self.search([
                    ('asset_id', '=', record.asset_id.id),
                    ('state', '=', 'assigned'),
                    ('id', '!=', record.id),
                ])
                if existing:
                    raise ValidationError(
                        _('Asset "%s" is already assigned to property "%s". '
                          'Please return it first before assigning to a new property.') %
                        (record.asset_id.name, existing[0].property_id.name)
                    )

    @api.constrains('expected_return_date', 'assignment_date')
    def _check_dates(self):
        for record in self:
            if record.expected_return_date and record.assignment_date:
                if record.expected_return_date < record.assignment_date:
                    raise ValidationError(
                        _('Expected return date cannot be earlier than assignment date.')
                    )

    def action_confirm(self):
        for record in self:
            if record.asset_id.asset_state in ('disposed', 'lost'):
                raise UserError(
                    _('Cannot assign asset "%s" because it is %s.') %
                    (record.asset_id.name, record.asset_id.asset_state)
                )
            record.write({
                'state': 'assigned',
            })
            record.asset_id.write({'asset_state': 'in_use'})

    def action_return(self):
        for record in self:
            record.write({
                'state': 'returned',
                'actual_return_date': fields.Date.today(),
            })
            # Check if there are any other active assignments
            other_assignments = self.search([
                ('asset_id', '=', record.asset_id.id),
                ('state', '=', 'assigned'),
                ('id', '!=', record.id),
            ])
            if not other_assignments:
                record.asset_id.write({'asset_state': 'available'})

    def action_cancel(self):
        for record in self:
            if record.state == 'assigned':
                # Check for other active assignments
                other_assignments = self.search([
                    ('asset_id', '=', record.asset_id.id),
                    ('state', '=', 'assigned'),
                    ('id', '!=', record.id),
                ])
                if not other_assignments:
                    record.asset_id.write({'asset_state': 'available'})
            record.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_acknowledge(self):
        self.write({
            'acknowledged': True,
            'acknowledged_date': fields.Datetime.now(),
        })

    def name_get(self):
        result = []
        for record in self:
            name = f"{record.name} - {record.asset_id.name} @ {record.property_id.name}"
            result.append((record.id, name))
        return result
