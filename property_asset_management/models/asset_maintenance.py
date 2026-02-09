# -*- coding: utf-8 -*-

from odoo import models, fields, api, _


class AssetMaintenance(models.Model):
    _name = 'asset.maintenance'
    _description = 'Asset Maintenance'
    _order = 'scheduled_date desc, id desc'
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
    property_category_id = fields.Many2one(
        'product.category',
        string='Property',
        compute='_compute_property_id',
        store=True,
    )
    maintenance_type = fields.Selection([
        ('preventive', 'Preventive'),
        ('corrective', 'Corrective'),
        ('inspection', 'Inspection'),
        ('calibration', 'Calibration'),
        ('upgrade', 'Upgrade'),
    ], string='Maintenance Type', default='preventive', required=True, tracking=True)

    # Schedule
    scheduled_date = fields.Date(
        string='Scheduled Date',
        required=True,
        tracking=True,
    )
    completion_date = fields.Date(
        string='Completion Date',
        tracking=True,
    )
    duration = fields.Float(
        string='Duration (Hours)',
    )

    # Assignment
    technician_id = fields.Many2one(
        'res.users',
        string='Technician',
        tracking=True,
    )
    vendor_id = fields.Many2one(
        'res.partner',
        string='Service Vendor',
        domain=[('is_company', '=', True)],
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    # Cost
    cost = fields.Float(
        string='Maintenance Cost',
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
    )

    # Status
    state = fields.Selection([
        ('draft', 'Draft'),
        ('scheduled', 'Scheduled'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', tracking=True, required=True)

    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], string='Priority', default='1')

    # Details
    description = fields.Text(
        string='Description',
    )
    work_performed = fields.Html(
        string='Work Performed',
    )
    parts_replaced = fields.Text(
        string='Parts Replaced',
    )
    findings = fields.Text(
        string='Findings',
    )
    recommendations = fields.Text(
        string='Recommendations',
    )

    # Condition
    condition_before = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('non_functional', 'Non-Functional'),
    ], string='Condition Before')
    condition_after = fields.Selection([
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('poor', 'Poor'),
        ('non_functional', 'Non-Functional'),
    ], string='Condition After')

    # Documents
    document_ids = fields.Many2many(
        'ir.attachment',
        'maintenance_attachment_rel',
        'maintenance_id',
        'attachment_id',
        string='Documents',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.maintenance') or _('New')
        return super().create(vals_list)

    @api.depends('asset_id', 'asset_id.current_property_category_id')
    def _compute_property_id(self):
        for record in self:
            record.property_category_id = record.asset_id.current_property_category_id

    def action_schedule(self):
        self.write({'state': 'scheduled'})

    def action_start(self):
        for record in self:
            record.write({'state': 'in_progress'})
            record.asset_id.write({'asset_state': 'maintenance'})

    def action_complete(self):
        for record in self:
            record.write({
                'state': 'done',
                'completion_date': fields.Date.today(),
            })
            # Check if there are any other in-progress maintenance
            other_maintenance = self.search([
                ('asset_id', '=', record.asset_id.id),
                ('state', '=', 'in_progress'),
                ('id', '!=', record.id),
            ])
            if not other_maintenance:
                # Check if asset has active assignment
                if record.asset_id.current_property_category_id:
                    record.asset_id.write({'asset_state': 'in_use'})
                else:
                    record.asset_id.write({'asset_state': 'available'})

    def action_cancel(self):
        for record in self:
            if record.state == 'in_progress':
                # Check for other in-progress maintenance
                other_maintenance = self.search([
                    ('asset_id', '=', record.asset_id.id),
                    ('state', '=', 'in_progress'),
                    ('id', '!=', record.id),
                ])
                if not other_maintenance:
                    if record.asset_id.current_property_category_id:
                        record.asset_id.write({'asset_state': 'in_use'})
                    else:
                        record.asset_id.write({'asset_state': 'available'})
            record.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})


class AssetMaintenanceRequest(models.Model):
    _name = 'asset.maintenance.request'
    _description = 'Asset Maintenance Request'
    _order = 'create_date desc'
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
    )
    property_category_id = fields.Many2one(
        'product.category',
        string='Property',
        related='asset_id.current_property_category_id',
        store=True,
    )
    requested_by_id = fields.Many2one(
        'res.users',
        string='Requested By',
        default=lambda self: self.env.user,
        required=True,
    )
    request_date = fields.Datetime(
        string='Request Date',
        default=fields.Datetime.now,
        required=True,
    )
    issue_description = fields.Text(
        string='Issue Description',
        required=True,
    )
    priority = fields.Selection([
        ('0', 'Low'),
        ('1', 'Normal'),
        ('2', 'High'),
        ('3', 'Critical'),
    ], string='Priority', default='1', required=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('maintenance_created', 'Maintenance Created'),
    ], string='Status', default='draft', tracking=True)
    maintenance_id = fields.Many2one(
        'asset.maintenance',
        string='Maintenance Record',
        readonly=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('asset.maintenance.request') or _('New')
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reject(self):
        self.write({'state': 'rejected'})

    def action_create_maintenance(self):
        for record in self:
            maintenance = self.env['asset.maintenance'].create({
                'asset_id': record.asset_id.id,
                'maintenance_type': 'corrective',
                'scheduled_date': fields.Date.today(),
                'description': record.issue_description,
                'priority': record.priority,
            })
            record.write({
                'state': 'maintenance_created',
                'maintenance_id': maintenance.id,
            })
        return True
