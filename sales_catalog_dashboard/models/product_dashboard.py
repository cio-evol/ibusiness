from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
from datetime import datetime, date

_logger = logging.getLogger(__name__)

class ProductDashboardMixin(models.AbstractModel):
    _name = 'product.dashboard.mixin'
    _description = 'Product Dashboard Mixin'

    dashboard_revenue = fields.Float(compute='_compute_dashboard_data', string='Revenue Dashboard')
    dashboard_cost = fields.Float(compute='_compute_dashboard_data', string='Cost Dashboard')
    dashboard_profit = fields.Float(compute='_compute_dashboard_data', string='Profit Dashboard')
    dashboard_graph_data = fields.Text(compute='_compute_dashboard_data', string='Graph Data')
    dashboard_rental_graph_data = fields.Text(compute='_compute_rental_dashboard_data', string='Rental Graph Data')

    product_payment_ids = fields.Many2many('account.payment', compute='_compute_product_payments', string='Payments Dashboard')
    product_rental_history_ids = fields.Many2many('sale.order.line', compute='_compute_product_rental_history', string='Rental History Dashboard')
    product_maintenance_ids = fields.Many2many('maintenance.request', compute='_compute_product_maintenance_history', string='Maintenance History Dashboard')
    product_invoice_ids = fields.Many2many('account.move.line', compute='_compute_product_invoice_history', string='Invoice History Dashboard')
    product_sale_order_ids = fields.Many2many('sale.order.line', compute='_compute_product_sale_history', string='Sales History Dashboard')
    product_vendor_bill_ids = fields.Many2many('account.move.line', compute='_compute_product_vendor_bill_history', string='Vendor Bills History Dashboard')

    current_owner_id = fields.Many2one('res.partner', compute='_compute_active_rental_data', string='Current Owner', store=False)
    dashboard_section_id = fields.Many2one('sales.catalog.section', string='Section')
    priority = fields.Selection([('0', 'Normal'), ('1', 'Favorite')], default='0', string="Favorite")
    last_sale_order_name = fields.Char(compute='_compute_active_rental_data', string='Current Rental Order', store=False)
    is_booked_today = fields.Boolean(compute='_compute_is_booked_today', string='Is Booked Today', store=False)
    is_property = fields.Boolean(string='Is Property', default=False)
    allocated_asset_ids = fields.One2many('sales.catalog.asset.allocation', 'parent_product_id', string='Allocated Assets')
    rental_report_image = fields.Image(string="Rental Report Image")
    x_analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')

    assignment_count = fields.Integer(compute='_compute_assignment_count', string='Assignments')
    maintenance_count = fields.Integer(compute='_compute_dashboard_counts', string='Maintenance Count')
    sale_order_count = fields.Integer(compute='_compute_dashboard_counts', string='Sales Count')
    invoice_count = fields.Integer(compute='_compute_dashboard_counts', string='Invoice Count')
    bill_count = fields.Integer(compute='_compute_dashboard_counts', string='Bill Count')
    repair_count = fields.Integer(compute='_compute_dashboard_counts', string='Repair Count')
    calendar_event_count = fields.Integer(compute='_compute_dashboard_counts', string='Calendar Event Count')
    document_count = fields.Integer(compute='_compute_dashboard_counts', string='Document Count')

    x_has_ongoing_booking = fields.Boolean(string="Has Ongoing Booking", compute='_compute_booking_status', store=False)
    x_current_booking_so = fields.Char(string="Current Booking SO", compute='_compute_booking_status', store=False)
    product_attribute_ids = fields.Many2many('product.attribute', compute='_compute_product_attribute_ids', string='Product Attributes', store=True)

    def _compute_assignment_count(self):
        for record in self:
            record.assignment_count = len(record.allocated_asset_ids)

    def _compute_dashboard_counts(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.maintenance_count = self.env['maintenance.request'].search_count(['|', ('equipment_id.product_id', 'in', variant_ids), ('product_id', 'in', variant_ids)])
            record.sale_order_count = self.env['sale.order'].search_count([('order_line.product_id', 'in', variant_ids), ('state', 'in', ['sale', 'done'])])
            record.invoice_count = self.env['account.move'].search_count([('invoice_line_ids.product_id', 'in', variant_ids), ('move_type', 'in', ['out_invoice', 'out_refund']), ('state', '!=', 'cancel')])
            record.bill_count = self.env['account.move'].search_count([('invoice_line_ids.product_id', 'in', variant_ids), ('move_type', 'in', ['in_invoice', 'in_refund']), ('state', '!=', 'cancel')])
            record.repair_count = self.env['repair.order'].search_count([('product_id', 'in', variant_ids)]) if 'repair.order' in self.env else 0
            record.calendar_event_count = self.env['calendar.event'].search_count([('res_model', '=', record._name), ('res_id', '=', record.id)]) if 'calendar.event' in self.env else 0
            record.document_count = self.env['documents.document'].search_count([('res_model', '=', record._name), ('res_id', '=', record.id)]) if 'documents.document' in self.env else 0

    @api.depends('attribute_line_ids', 'attribute_line_ids.attribute_id')
    def _compute_product_attribute_ids(self):
        for record in self:
            record.product_attribute_ids = record.attribute_line_ids.mapped('attribute_id')

    def _compute_booking_status(self):
        today = fields.Date.context_today(self)
        sol = self.env['sale.order.line']
        has_custom_start = hasattr(sol, 'x_rental_start')
        has_custom_end = hasattr(sol, 'x_rental_end')
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            lines = sol.search([('product_id', 'in', variant_ids), ('state', 'in', ['sale', 'done'])])
            ongoing_orders = []
            for line in lines:
                s_date = line.x_rental_start if has_custom_start and line.x_rental_start else (line.start_date if line.is_rental else False)
                e_date = line.x_rental_end if has_custom_end and line.x_rental_end else (line.return_date if line.is_rental else False)
                if s_date:
                    start_val = s_date.date() if isinstance(s_date, datetime) else s_date
                    if e_date:
                        end_val = e_date.date() if isinstance(e_date, datetime) else e_date
                        if start_val <= today <= end_val: ongoing_orders.append(line.order_id)
                    else:
                        if start_val <= today: ongoing_orders.append(line.order_id)
                else: ongoing_orders.append(line.order_id)
            if ongoing_orders:
                latest_order = sorted(list(set(ongoing_orders)), key=lambda o: o.date_order or datetime.min, reverse=True)[0]
                record.x_has_ongoing_booking, record.x_current_booking_so = True, latest_order.name
            else: record.x_has_ongoing_booking, record.x_current_booking_so = False, False

    def _compute_dashboard_data(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            invoice_lines = self.env['account.move.line'].search([('product_id', 'in', variant_ids), ('parent_state', '=', 'posted'), ('move_type', '=', 'out_invoice')])
            revenue = sum(line.price_subtotal for line in invoice_lines)
            bill_lines = self.env['account.move.line'].search([('product_id', 'in', variant_ids), ('parent_state', '=', 'posted'), ('move_type', '=', 'in_invoice')])
            cost = sum(line.price_subtotal for line in bill_lines)
            record.dashboard_revenue, record.dashboard_cost, record.dashboard_profit = revenue, cost, revenue - cost
            record.dashboard_graph_data = json.dumps([{'key': 'Profit', 'values': [{'label': 'Revenue', 'value': revenue}, {'label': 'Cost', 'value': cost}, {'label': 'Profit', 'value': revenue - cost}]}])

    def _compute_rental_dashboard_data(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            rental_lines = self.env['sale.order.line'].search([('product_id', 'in', variant_ids), ('is_rental', '=', True), ('state', 'in', ['draft', 'sent', 'sale', 'done'])])
            data_by_status, all_dates = {}, set()
            for line in rental_lines:
                status, date_val = line.rental_status or 'undefined', line.start_date or line.order_id.date_order
                if not date_val: continue
                date_label = (date_val.date() if isinstance(date_val, datetime) else date_val).strftime('%d %b %Y')
                data_by_status.setdefault(status, {})[date_label] = data_by_status.get(status, {}).get(date_label, 0.0) + line.product_uom_qty
                all_dates.add(date_label)
            unique_dates_list = sorted(list(all_dates), key=lambda l: datetime.strptime(l, '%d %b %Y').date())
            graph_data, status_map = [], {
                'draft': {'label': 'Quotation', 'color': '#17a2b8'}, 'sent': {'label': 'Sent', 'color': '#17a2b8'},
                'pickup': {'label': 'Reserved', 'color': '#ffc107'}, 'return': {'label': 'Picked Up', 'color': '#fd7e14'},
                'returned': {'label': 'Returned', 'color': '#28a745'}, 'cancel': {'label': 'Cancelled', 'color': '#dc3545'},
                'undefined': {'label': 'Undefined', 'color': '#6c757d'}
            }
            for status, date_values in data_by_status.items():
                graph_data.append({
                    'key': status_map.get(status, {}).get('label', status.capitalize()),
                    'values': [{'label': d, 'value': date_values.get(d, 0.0)} for d in unique_dates_list],
                    'color': status_map.get(status, {}).get('color', '#6c757d'), 'type': 'bar'
                })
            record.dashboard_rental_graph_data = json.dumps(graph_data or [{'key': 'No Data', 'values': []}])

    def action_open_rental_analysis(self):
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sales_catalog_dashboard.action_rental_reporting")
        action.update({'name': f"Rental Analysis - {self.name}", 'domain': [('product_id.product_tmpl_id', '=', self.id if self._name == 'product.template' else self.product_tmpl_id.id), ('is_rental', '=', True), ('state', 'in', ['sale', 'done'])]})
        return action

    def action_field_visit(self):
        self.ensure_one()
        return {
            'name': 'Field Visit', 'type': 'ir.actions.act_window', 'res_model': 'project.task', 'view_mode': 'form', 'target': 'current',
            'context': {
                'default_name': f'Field Visit: {self.name}', 'default_partner_id': self.current_owner_id.id,
                'default_sale_line_id': self.env['sale.order.line'].search([('product_id', 'in', self.product_variant_ids.ids if self._name == 'product.template' else self.ids), ('state', 'in', ['sale', 'done']), ('is_rental', '=', True)], limit=1).id,
                'default_description': f'Field Visit for Product: {self.name}'
            }
        }

    def action_help_desk(self):
        self.ensure_one()
        return {
            'name': 'Help Desk', 'type': 'ir.actions.act_window', 'res_model': 'helpdesk.ticket', 'view_mode': 'form', 'target': 'current',
            'context': {
                'default_name': f'Support Request: {self.name}', 'default_partner_id': self.current_owner_id.id,
                'default_product_id': self.product_variant_id.id if self._name == 'product.template' else self.id,
                'default_description': f'Issue reported for Product: {self.name}'
            }
        }

    def action_maintain(self):
        self.ensure_one()
        return {
            'name': 'Maintenance Request', 'type': 'ir.actions.act_window', 'res_model': 'maintenance.request', 'view_mode': 'form', 'target': 'current',
            'context': {
                'default_name': f'Maintenance Request for {self.name}', 'default_partner_id': self.current_owner_id.id,
                'default_description': f'Maintenance requested for Product: {self.name}',
                'default_product_id': self.product_variant_id.id if self._name == 'product.template' else self.id,
            }
        }

    def action_check_in(self):
        self.ensure_one()
        rental_line = self.env['sale.order.line'].search([('product_id', 'in', self.product_variant_ids.ids if self._name == 'product.template' else self.ids), ('is_rental', '=', True), ('state', '=', 'sale'), ('rental_status', '=', 'pickup')], order='start_date desc, create_date desc', limit=1)
        if not rental_line: raise UserError(_("No booking rental found for this product. Please create/confirm a booking first."))
        return rental_line.order_id.action_open_pickup()

    def action_check_out(self):
        self.ensure_one()
        rental_line = self.env['sale.order.line'].search([('product_id', 'in', self.product_variant_ids.ids if self._name == 'product.template' else self.ids), ('is_rental', '=', True), ('state', 'in', ['sale', 'done']), ('rental_status', '=', 'return')], order='start_date desc, create_date desc', limit=1)
        if not rental_line: raise UserError(_("No picked-up rental found for this product. Please pickup/confirm a rental first."))
        return rental_line.order_id.action_open_return()

    def action_sign_agreement(self): pass
    def action_parking_allocations(self): pass

    def action_asset_allocations(self):
        self.ensure_one()
        # Filter by this specific property (variant) so different properties don't show mixed
        parent_id = self.product_variant_id.id if self._name == 'product.template' else self.id
        return {
            'name': _('Assets Allocation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.asset.allocation',
            'view_mode': 'list',
            'view_id': self.env.ref('sales_catalog_dashboard.view_sales_catalog_asset_allocation_list', raise_if_not_found=False).id,
            'search_view_id': self.env.ref('sales_catalog_dashboard.view_sales_catalog_asset_allocation_search', raise_if_not_found=False).id,
            'domain': [('parent_product_id', '=', parent_id)],
            'context': {
                'default_parent_product_id': parent_id,
                # No group_by when viewing one property (already filtered)
            },
            'target': 'current',
        }

    def action_open_documents(self):
        self.ensure_one()
        return {'name': 'Documents', 'type': 'ir.actions.act_window', 'res_model': 'documents.document', 'view_mode': 'kanban,list,form', 'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)], 'context': {'default_res_model': self._name, 'default_res_id': self.id}}

    def action_open_product_profile(self):
        self.ensure_one()
        view_id = self.env.ref('product.product_template_form_view').id if self._name == 'product.template' else self.env.ref('product.product_normal_form_view').id
        return {'name': 'Product Profile', 'type': 'ir.actions.act_window', 'res_model': self._name, 'res_id': self.id, 'view_mode': 'form', 'view_id': view_id, 'target': 'current'}

    def action_open_website_url(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_url', 'url': self.website_url, 'target': 'new'}

    def action_view_rental_schedule(self):
        self.ensure_one()
        variant_id = self.product_variant_id.id if self._name == 'product.template' else self.id
        return {'name': 'Schedule', 'type': 'ir.actions.act_window', 'res_model': 'sale.order.line', 'view_mode': 'gantt,list,form', 'domain': [('product_id', '=', variant_id), ('is_rental', '=', True)], 'context': {'search_default_product_id': variant_id, 'default_product_id': variant_id, 'in_rental_app': 1, 'in_rental_schedule': 1}}

    def action_view_rental_calendar(self):
        self.ensure_one()
        variant_id = self.product_variant_id.id if self._name == 'product.template' else self.id
        return {'name': 'Calendar', 'type': 'ir.actions.act_window', 'res_model': 'sale.order.line', 'view_mode': 'calendar,list,form', 'domain': [('product_id', '=', variant_id), ('is_rental', '=', True)], 'context': {'default_product_id': variant_id, 'default_is_rental': True}}

    def _compute_active_rental_data(self):
        today = fields.Date.context_today(self)
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            line = self.env['sale.order.line'].search([('product_id', 'in', variant_ids), ('is_rental', '=', True), ('state', 'in', ['sale', 'done']), ('rental_status', 'in', ['pickup', 'return']), ('start_date', '<=', today), ('return_date', '>=', today)], limit=1)
            record.last_sale_order_name, record.current_owner_id = (line.order_id.name, line.order_partner_id) if line else (False, False)

    def _compute_is_booked_today(self):
        today = fields.Date.context_today(self)
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.is_booked_today = bool(self.env['sale.order.line'].search_count([('product_id', 'in', variant_ids), ('is_rental', '=', True), ('state', 'in', ['sale', 'done']), ('rental_status', 'in', ['pickup', 'return']), ('start_date', '<=', today), ('return_date', '>=', today)]))

    def _compute_product_payments(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            invoices = self.env['account.move.line'].search([('product_id', 'in', variant_ids), ('parent_state', '=', 'posted'), ('move_type', '=', 'out_invoice')]).mapped('move_id')
            record.product_payment_ids = self.env['account.payment'].search([('reconciled_invoice_ids', 'in', invoices.ids)]) if invoices else False

    def _compute_product_rental_history(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.product_rental_history_ids = self.env['sale.order.line'].search([('product_id', 'in', variant_ids), ('is_rental', '=', True), ('state', 'in', ['sale', 'done'])], order='start_date desc')

    def _compute_product_maintenance_history(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.product_maintenance_ids = self.env['maintenance.request'].search(['|', ('equipment_id.product_id', 'in', variant_ids), ('product_id', 'in', variant_ids)])

    def _compute_product_invoice_history(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.product_invoice_ids = self.env['account.move.line'].search([('product_id', 'in', variant_ids), ('parent_state', '=', 'posted'), ('move_type', '=', 'out_invoice')], order='date desc')

    def _compute_product_sale_history(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.product_sale_order_ids = self.env['sale.order.line'].search([('product_id', 'in', variant_ids), ('state', 'in', ['sale', 'done']), ('is_rental', '=', False)], order='order_id desc')

    def _compute_product_vendor_bill_history(self):
        for record in self:
            variant_ids = record.product_variant_ids.ids if record._name == 'product.template' else record.ids
            record.product_vendor_bill_ids = self.env['account.move.line'].search([('product_id', 'in', variant_ids), ('parent_state', '=', 'posted'), ('move_type', '=', 'in_invoice')], order='date desc')

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_property = fields.Boolean(string='Property')
    x_analytic_account_id = fields.Many2one('account.analytic.account', string='Analytic Account')

class ProductProduct(models.Model):
    _inherit = 'product.product'

    is_property = fields.Boolean(string='Property', related='product_tmpl_id.is_property')
    x_analytic_account_id = fields.Many2one('account.analytic.account', related='product_tmpl_id.x_analytic_account_id', string='Analytic Account', readonly=False)
    x_warehouse_id = fields.Many2one('stock.warehouse', string='Main Warehouse', help='Main warehouse for this property (e.g. for parking allocation).')

    # Dashboard fields (required by dashboard form view)
    x_has_ongoing_booking = fields.Boolean(compute='_compute_x_booking_status', string='Has Ongoing Booking')
    x_current_booking_so = fields.Char(compute='_compute_x_booking_status', string='Current Booking SO')
    dashboard_revenue = fields.Float(compute='_compute_dashboard_amounts', string='Revenue')
    dashboard_cost = fields.Float(compute='_compute_dashboard_amounts', string='Cost')
    dashboard_profit = fields.Float(compute='_compute_dashboard_amounts', string='Profit')
    current_owner_id = fields.Many2one('res.partner', compute='_compute_current_owner', string='Current Owner')
    priority = fields.Selection([('0', 'Normal'), ('1', 'Favorite')], default='0', string='Favorite')
    dashboard_rental_graph_data = fields.Text(compute='_compute_dashboard_rental_graph', string='Rental Graph Data')
    allocated_asset_ids = fields.One2many('sales.catalog.asset.allocation', 'parent_product_id', string='Allocated Assets')
    allocated_parking_ids = fields.One2many('sales.catalog.parking.allocation', 'parent_product_id', string='Parking Allocations')
    other_item_ids = fields.One2many('product.product.other.item', 'parent_product_id', string='Other Items')
    product_payment_ids = fields.Many2many('account.payment', compute='_compute_product_payment_ids', string='Payments')
    product_rental_history_ids = fields.Many2many('sale.order.line', compute='_compute_product_rental_history_ids', string='Rental History')
    product_maintenance_ids = fields.Many2many('maintenance.request', compute='_compute_product_maintenance_ids', string='Maintenance')
    product_invoice_ids = fields.Many2many('account.move.line', compute='_compute_product_invoice_ids', string='Invoices')
    product_sale_order_ids = fields.Many2many('sale.order.line', compute='_compute_product_sale_order_ids', string='Sales')
    product_vendor_bill_ids = fields.Many2many('account.move.line', compute='_compute_product_vendor_bill_ids', string='Vendor Bills')
    product_attribute_ids = fields.Many2many(
        'product.attribute',
        compute='_compute_product_attribute_ids',
        string='Attributes',
        store=True,
    )
    # Stored copy of template + variant tags for search panel (all_product_tag_ids is computed only)
    x_product_tag_ids = fields.Many2many(
        'product.tag',
        compute='_compute_x_product_tag_ids',
        string='Tags',
        store=True,
    )

    @api.depends('product_tmpl_id', 'product_tmpl_id.product_tag_ids', 'additional_product_tag_ids')
    def _compute_x_product_tag_ids(self):
        for rec in self:
            base = rec.product_tmpl_id.product_tag_ids if rec.product_tmpl_id else self.env['product.tag']
            rec.x_product_tag_ids = (base | rec.additional_product_tag_ids).sorted('sequence')

    def _compute_x_booking_status(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.x_has_ongoing_booking = False
            rec.x_current_booking_so = False
            line = self.env['sale.order.line'].search([
                ('product_id', '=', rec.id),
                ('is_rental', '=', True),
                ('state', 'in', ['sale', 'done']),
                ('rental_status', 'in', ['pickup', 'return']),
                ('start_date', '<=', today),
                ('return_date', '>=', today),
            ], limit=1)
            if line:
                rec.x_has_ongoing_booking = True
                rec.x_current_booking_so = line.order_id.name or ''

    @api.depends('x_analytic_account_id')
    def _compute_dashboard_amounts(self):
        for rec in self:
            rec.dashboard_revenue = 0.0
            rec.dashboard_cost = 0.0
            rec.dashboard_profit = 0.0
            if rec.x_analytic_account_id:
                # Revenue & Cost from posted invoice/bill lines with this property's analytic account; Profit = Revenue - Cost
                analytic_lines = self.env['account.analytic.line'].search([
                    ('account_id', '=', rec.x_analytic_account_id.id),
                    ('move_line_id', '!=', False),
                ])
                move_line_ids = analytic_lines.mapped('move_line_id').ids
                if move_line_ids:
                    # Revenue: customer invoice lines (out_invoice)
                    out_lines = self.env['account.move.line'].search([
                        ('id', 'in', move_line_ids),
                        ('parent_state', '=', 'posted'),
                        ('move_type', '=', 'out_invoice'),
                    ])
                    rec.dashboard_revenue = sum(out_lines.mapped('price_subtotal'))
                    # Cost: vendor bill lines (in_invoice), same analytic-account scenario
                    in_lines = self.env['account.move.line'].search([
                        ('id', 'in', move_line_ids),
                        ('parent_state', '=', 'posted'),
                        ('move_type', '=', 'in_invoice'),
                    ])
                    rec.dashboard_cost = sum(in_lines.mapped('price_subtotal'))
                rec.dashboard_profit = rec.dashboard_revenue - rec.dashboard_cost

    def _compute_current_owner(self):
        today = fields.Date.context_today(self)
        for rec in self:
            rec.current_owner_id = False
            line = self.env['sale.order.line'].search([
                ('product_id', '=', rec.id),
                ('is_rental', '=', True),
                ('state', 'in', ['sale', 'done']),
                ('rental_status', 'in', ['pickup', 'return']),
                ('start_date', '<=', today),
                ('return_date', '>=', today),
            ], limit=1)
            if line:
                rec.current_owner_id = line.order_partner_id

    def _compute_dashboard_rental_graph(self):
        for rec in self:
            rec.dashboard_rental_graph_data = '{}'

    def _compute_product_payment_ids(self):
        for rec in self:
            rec.product_payment_ids = False

    def _compute_product_rental_history_ids(self):
        for rec in self:
            rec.product_rental_history_ids = self.env['sale.order.line']

    def _compute_product_maintenance_ids(self):
        for rec in self:
            rec.product_maintenance_ids = self.env['maintenance.request']

    def _compute_product_invoice_ids(self):
        for rec in self:
            rec.product_invoice_ids = self.env['account.move.line']

    def _compute_product_sale_order_ids(self):
        for rec in self:
            rec.product_sale_order_ids = self.env['sale.order.line']

    def _compute_product_vendor_bill_ids(self):
        for rec in self:
            rec.product_vendor_bill_ids = self.env['account.move.line']

    @api.depends('product_tmpl_id', 'product_tmpl_id.attribute_line_ids')
    def _compute_product_attribute_ids(self):
        for rec in self:
            rec.product_attribute_ids = rec.product_tmpl_id.attribute_line_ids.mapped('attribute_id') if rec.product_tmpl_id else self.env['product.attribute']

    # Stub actions for dashboard form view (full implementations are in commented mixin)
    def action_field_visit(self):
        pass

    def action_help_desk(self):
        pass

    def action_maintain(self):
        pass

    def action_check_in(self):
        pass

    def action_check_out(self):
        pass

    def action_sign_agreement(self):
        pass

    def action_parking_allocations(self):
        self.ensure_one()
        return {
            'name': _('Parking Allocations'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.parking.allocation',
            'view_mode': 'list,form',
            'domain': [('parent_product_id', '=', self.id)],
            'context': {'default_parent_product_id': self.id},
            'target': 'current',
        }

    def action_asset_allocations(self):
        self.ensure_one()
        parent_id = self.id
        return {
            'name': _('Assets Allocation'),
            'type': 'ir.actions.act_window',
            'res_model': 'sales.catalog.asset.allocation',
            'view_mode': 'list',
            'view_id': self.env.ref('sales_catalog_dashboard.view_sales_catalog_asset_allocation_list', raise_if_not_found=False).id,
            'search_view_id': self.env.ref('sales_catalog_dashboard.view_sales_catalog_asset_allocation_search', raise_if_not_found=False).id,
            'domain': [('parent_product_id', '=', parent_id)],
            'context': {'default_parent_product_id': parent_id},
            'target': 'current',
        }

    def action_open_documents(self):
        self.ensure_one()
        return {
            'name': _('Documents'),
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'kanban,list,form',
            'domain': [('res_model', '=', self._name), ('res_id', '=', self.id)],
            'context': {'default_res_model': self._name, 'default_res_id': self.id},
        }

    def action_open_product_profile(self):
        self.ensure_one()
        return {
            'name': _('Product Profile'),
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_open_website_url(self):
        self.ensure_one()
        if getattr(self, 'website_url', None):
            return {'type': 'ir.actions.act_url', 'url': self.website_url, 'target': 'new'}
        return False

    def action_view_rental_schedule(self):
        self.ensure_one()
        return {
            'name': _('Schedule'),
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'gantt,list,form',
            'domain': [('product_id', '=', self.id), ('is_rental', '=', True)],
            'context': {
                'default_product_id': self.id,
                'default_is_rental': True,
                'in_rental_app': 1,
                'in_rental_schedule': 1,
                # So creating from Gantt (select date range) uses this product and maps dates to rental
                'convert_default_order_line_values': 1,
            },
        }

class SalesCatalogSection(models.Model):
    _name = 'sales.catalog.section'
    _description = 'Sales Catalog Section'
    _order = 'name'

    name = fields.Char(required=True)
