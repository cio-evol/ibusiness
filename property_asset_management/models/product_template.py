# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    # Asset Fields
    is_asset = fields.Boolean(
        string='Is an Asset',
        default=False,
        help='Check if this product is a trackable asset',
    )
    is_property = fields.Boolean(
        string='Is a Property',
        default=False,
        help='Check if this product represents a property (building, room, etc.)',
    )
    asset_category_id = fields.Many2one(
        'asset.category',
        string='Asset Category',
        help='Category of the asset for classification',
    )
    property_type_id = fields.Many2one(
        'property.type',
        string='Property Type',
        help='Type of property if this is a property product',
    )

    # Asset Identification
    asset_code = fields.Char(
        string='Asset Code',
        copy=False,
        help='Unique identifier for the asset',
    )
    serial_number = fields.Char(
        string='Serial Number',
        copy=False,
    )
    barcode_asset = fields.Char(
        string='Asset Barcode',
        copy=False,
    )

    # Asset Details
    brand = fields.Char(string='Brand')
    model_name = fields.Char(string='Model')
    manufacturer_id = fields.Many2one(
        'res.partner',
        string='Manufacturer',
        domain=[('is_company', '=', True)],
    )
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True)],
    )

    # Purchase & Value
    purchase_date = fields.Date(string='Purchase Date')
    purchase_price = fields.Float(string='Purchase Price')
    warranty_start_date = fields.Date(string='Warranty Start Date')
    warranty_end_date = fields.Date(string='Warranty End Date')
    warranty_status = fields.Selection([
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('none', 'No Warranty'),
    ], string='Warranty Status', compute='_compute_warranty_status', store=True)

    # Depreciation
    depreciation_years = fields.Integer(
        string='Depreciation Years',
        default=5,
    )
    current_value = fields.Float(
        string='Current Value',
        compute='_compute_current_value',
        store=True,
    )
    salvage_value = fields.Float(
        string='Salvage Value',
        default=0.0,
    )

    # Asset Status
    asset_state = fields.Selection([
        ('new', 'New'),
        ('in_use', 'In Use'),
        ('available', 'Available'),
        ('maintenance', 'Under Maintenance'),
        ('repair', 'Under Repair'),
        ('disposed', 'Disposed'),
        ('lost', 'Lost'),
    ], string='Asset Status', default='new', tracking=True)

    # Assignment
    current_property_id = fields.Many2one(
        'property.property',
        string='Current Property',
        compute='_compute_current_assignment',
        store=True,
    )
    current_user_id = fields.Many2one(
        'res.users',
        string='Current User',
        compute='_compute_current_assignment',
        store=True,
    )
    assignment_ids = fields.One2many(
        'asset.assignment',
        'asset_id',
        string='Assignment History',
    )
    assignment_count = fields.Integer(
        string='Assignment Count',
        compute='_compute_assignment_count',
    )

    # Maintenance
    maintenance_ids = fields.One2many(
        'asset.maintenance',
        'asset_id',
        string='Maintenance Records',
    )
    maintenance_count = fields.Integer(
        string='Maintenance Count',
        compute='_compute_maintenance_count',
    )
    next_maintenance_date = fields.Date(
        string='Next Maintenance Date',
        compute='_compute_next_maintenance',
        store=True,
    )
    requires_maintenance = fields.Boolean(
        string='Requires Maintenance',
        related='asset_category_id.requires_maintenance',
        store=True,
    )

    # Documents
    document_ids = fields.Many2many(
        'ir.attachment',
        'product_asset_attachment_rel',
        'product_id',
        'attachment_id',
        string='Documents',
    )

    @api.depends('warranty_start_date', 'warranty_end_date')
    def _compute_warranty_status(self):
        today = fields.Date.today()
        for record in self:
            if not record.warranty_end_date:
                record.warranty_status = 'none'
            elif record.warranty_end_date >= today:
                record.warranty_status = 'active'
            else:
                record.warranty_status = 'expired'

    @api.depends('purchase_price', 'purchase_date', 'depreciation_years', 'salvage_value')
    def _compute_current_value(self):
        today = fields.Date.today()
        for record in self:
            if record.purchase_date and record.purchase_price and record.depreciation_years:
                years_passed = (today - record.purchase_date).days / 365.25
                if years_passed >= record.depreciation_years:
                    record.current_value = record.salvage_value
                else:
                    annual_depreciation = (record.purchase_price - record.salvage_value) / record.depreciation_years
                    depreciated = annual_depreciation * years_passed
                    record.current_value = record.purchase_price - depreciated
            else:
                record.current_value = record.purchase_price or record.list_price

    @api.depends('assignment_ids', 'assignment_ids.state')
    def _compute_current_assignment(self):
        for record in self:
            current_assignment = record.assignment_ids.filtered(
                lambda a: a.state == 'assigned'
            )[:1]
            record.current_property_id = current_assignment.property_id.id if current_assignment else False
            record.current_user_id = current_assignment.assigned_to_id.id if current_assignment else False

    @api.depends('assignment_ids')
    def _compute_assignment_count(self):
        for record in self:
            record.assignment_count = len(record.assignment_ids)

    @api.depends('maintenance_ids')
    def _compute_maintenance_count(self):
        for record in self:
            record.maintenance_count = len(record.maintenance_ids)

    @api.depends('maintenance_ids', 'maintenance_ids.state', 'maintenance_ids.scheduled_date',
                 'asset_category_id.maintenance_frequency')
    def _compute_next_maintenance(self):
        today = fields.Date.today()
        for record in self:
            # Check for scheduled maintenance
            scheduled = record.maintenance_ids.filtered(
                lambda m: m.state in ('draft', 'scheduled') and m.scheduled_date >= today
            ).sorted('scheduled_date')[:1]
            if scheduled:
                record.next_maintenance_date = scheduled.scheduled_date
            elif record.requires_maintenance and record.asset_category_id.maintenance_frequency:
                # Calculate based on last maintenance
                last_maintenance = record.maintenance_ids.filtered(
                    lambda m: m.state == 'done'
                ).sorted('completion_date', reverse=True)[:1]
                if last_maintenance and last_maintenance.completion_date:
                    record.next_maintenance_date = last_maintenance.completion_date + relativedelta(
                        days=record.asset_category_id.maintenance_frequency
                    )
                elif record.purchase_date:
                    record.next_maintenance_date = record.purchase_date + relativedelta(
                        days=record.asset_category_id.maintenance_frequency
                    )
                else:
                    record.next_maintenance_date = False
            else:
                record.next_maintenance_date = False

    @api.onchange('asset_category_id')
    def _onchange_asset_category_id(self):
        if self.asset_category_id:
            self.depreciation_years = self.asset_category_id.default_depreciation_years

    @api.onchange('is_asset')
    def _onchange_is_asset(self):
        if self.is_asset:
            self.is_property = False
            self.tracking = 'serial'

    @api.onchange('is_property')
    def _onchange_is_property(self):
        if self.is_property:
            self.is_asset = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('is_asset') and not vals.get('asset_code'):
                vals['asset_code'] = self.env['ir.sequence'].next_by_code('product.asset') or ''
        return super().create(vals_list)

    @api.constrains('asset_category_id', 'serial_number')
    def _check_serial_requirement(self):
        for record in self:
            if record.is_asset and record.asset_category_id and record.asset_category_id.requires_serial:
                if not record.serial_number:
                    raise ValidationError(
                        _('Serial number is required for assets in category "%s"') %
                        record.asset_category_id.name
                    )

    def action_view_assignments(self):
        self.ensure_one()
        return {
            'name': _('Assignment History'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.assignment',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_view_maintenance(self):
        self.ensure_one()
        return {
            'name': _('Maintenance Records'),
            'type': 'ir.actions.act_window',
            'res_model': 'asset.maintenance',
            'view_mode': 'list,form',
            'domain': [('asset_id', '=', self.id)],
            'context': {'default_asset_id': self.id},
        }

    def action_set_available(self):
        self.write({'asset_state': 'available'})

    def action_set_maintenance(self):
        self.write({'asset_state': 'maintenance'})

    def action_dispose(self):
        # Return all active assignments first
        active_assignments = self.assignment_ids.filtered(lambda a: a.state == 'assigned')
        active_assignments.action_return()
        self.write({'asset_state': 'disposed'})
