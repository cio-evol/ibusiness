from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging
from datetime import datetime, date

_logger = logging.getLogger(__name__)

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    dashboard_revenue = fields.Float(compute='_compute_dashboard_data', string='Revenue')
    dashboard_cost = fields.Float(compute='_compute_dashboard_data', string='Cost')
    

    dashboard_profit = fields.Float(compute='_compute_dashboard_data', string='Profit')
    dashboard_graph_data = fields.Text(compute='_compute_dashboard_data', string='Graph Data')
    
    dashboard_rental_graph_data = fields.Text(compute='_compute_dashboard_rental_graph_data', string='Rental Graph Data')

    def _compute_dashboard_rental_graph_data(self):
        for product in self:
            # Fetch rental report data grouped by date:month and state
            # We want to show price (revenue) or quantity? User said "rental-related metrics". 
            # Stacked graph usually shows volume or price. Let's use price (revenue) as it's most common.
            # Domain: product_id = product.id
            domain = [('product_tmpl_id', '=', product.id)]
            
            # We can't easily group by month in a simple search. We need read_group.
            data = self.env['sale.rental.report'].read_group(
                domain,
                ['date:month', 'state', 'price'],
                ['date:month', 'state'],
                lazy=False
            )
            
            # Transform into JSON for the widget
            # Expected structure: [ { key: "State", values: [{label: "Month", value: X}] }, ... ]
            
            datasets = {}
            # Organize by state first
            for row in data:
                state = row['state']
                month_label = row['date:month']
                price = row['price']
                
                if state not in datasets:
                    datasets[state] = {}
                
                datasets[state][month_label] = price

            # Get all unique months to sort them?
            # read_group usually returns sorted by group_by fields if order is not specified?
            # Validating order might be complex, let's trust read_group or simple sort.
            
            # Convert to list format
            formatted_data = []
            
            # Define colors for states if possible, or let JS handle it.
            # JS uses getColor if no color provided.
            
            for state, month_data in datasets.items():
                values = []
                for month, price in month_data.items():
                    values.append({'label': month, 'value': price})
                
                formatted_data.append({
                    'key': state,
                    'values': values
                })

            product.dashboard_rental_graph_data = json.dumps(formatted_data)
    
    product_payment_ids = fields.Many2many(
        'account.payment',
        compute='_compute_product_payments',
        string='Payments'
    )
    
    product_rental_history_ids = fields.Many2many(
        'sale.order.line',
        compute='_compute_product_rental_history',
        string='Rental History'
    )
    
    product_maintenance_ids = fields.Many2many(
        'maintenance.request',
        compute='_compute_product_maintenance_history',
        string='Maintenance History'
    )

    product_invoice_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_product_invoice_history',
        string='Invoice History'
    )
    
    product_sale_order_ids = fields.Many2many(
        'sale.order.line',
        compute='_compute_product_sale_history',
        string='Sales History'
    )

    product_vendor_bill_ids = fields.Many2many(
        'account.move.line',
        compute='_compute_product_vendor_bill_history',
        string='Vendor Bills History'
    )
    
    # Computed fields for active rental data
    current_owner_id = fields.Many2one(
        'res.partner', 
        compute='_compute_active_rental_data', 
        string='Current Owner'
    )
    dashboard_section_id = fields.Many2one('sales.catalog.section', string='Section')
    priority = fields.Selection(
        [('0', 'Normal'), ('1', 'Favorite')],
        default='0',
        string="Favorite",
    )
    
    last_sale_order_name = fields.Char(
        compute='_compute_active_rental_data', 
        string='Current Rental Order',
        store=False
    )
    
    is_booked_today = fields.Boolean(
        compute='_compute_is_booked_today',
        string='Is Booked Today',
        store=False
    )

    rental_report_image = fields.Image(string="Rental Report Image")

    # Computed many2many field for product attributes (for searchpanel filtering)
    product_attribute_ids = fields.Many2many(
        'product.attribute',
        compute='_compute_product_attribute_ids',
        string='Product Attributes',
        store=True
    )

    x_has_ongoing_booking = fields.Boolean(
        string="Has Ongoing Booking",
        compute='_compute_booking_status',
        store=False
    )
    x_current_booking_so = fields.Char(
        string="Current Booking SO",
        compute='_compute_booking_status',
        store=False
    )

    def _compute_booking_status(self):
        today = fields.Date.context_today(self)
        try:
             _logger.info(f"Computing booking status for products: {self.ids} on {today}")
        except Exception:
             pass
        
        # Check if custom rental fields exist on sale.order.line
        has_custom_start = hasattr(self.env['sale.order.line'], 'x_rental_start')
        has_custom_end = hasattr(self.env['sale.order.line'], 'x_rental_end')
        
        for product in self:
            _logger.info(f"Checking product: {product.name} ({product.id})")

            # 1. Find sale.order.line for product variants
            # We need lines where the parent order is confirmed/done
            domain = [
                ('product_id', 'in', product.product_variant_ids.ids),
                ('state', 'in', ['sale', 'done']),
                # We don't filter by 'is_rental' strictly if we are falling back to simple SO logic
                # But typically 'booking' requires rental. Let's keep is_rental if we find standard fields, 
                # or just look for the custom fields.
                # User said: "Find sale.order.line... Parent sale.order must be in state ['sale','done']"
                # They didn't explicitly say "is_rental=True" for the fallback.
            ]
            
            # Search all confirmed lines for this product
            lines = self.env['sale.order.line'].search(domain)
            
            ongoing_orders = []
            for line in lines:
                # Use custom fields if available, else standard rental fields, else None
                s_date = False
                e_date = False
                
                if has_custom_start and line.x_rental_start:
                    s_date = line.x_rental_start
                    e_date = line.x_rental_end if has_custom_end else False
                elif line.is_rental and line.start_date:
                    s_date = line.start_date
                    e_date = line.return_date
                
                # Logic:
                # If booking fields exist (custom or standard found):
                if s_date:
                    # today must be between start and end.
                    # If end date is empty, treat as ongoing if start <= today.
                    start_val = s_date.date() if isinstance(s_date, datetime) else s_date
                    
                    if e_date:
                        end_val = e_date.date() if isinstance(e_date, datetime) else e_date
                        if start_val <= today <= end_val:
                            ongoing_orders.append(line.order_id)
                    else:
                        if start_val <= today:
                            ongoing_orders.append(line.order_id)
                else:
                    # If no booking fields exist/populated, fallback to confirmed SO logic
                    # "If no booking fields exist, fallback: confirmed sale order line exists"
                    # This implies ANY confirmed line is considered "ongoing" if dates are missing.
                    ongoing_orders.append(line.order_id)

            if ongoing_orders:
                # Sort by order date descending
                unique_orders = list(set(ongoing_orders))
                unique_orders.sort(key=lambda o: o.date_order or datetime.min, reverse=True)
                
                latest_order = unique_orders[0]
                product.x_has_ongoing_booking = True
                product.x_current_booking_so = latest_order.name
            else:
                product.x_has_ongoing_booking = False
                product.x_current_booking_so = False






    @api.depends('attribute_line_ids', 'attribute_line_ids.attribute_id')
    def _compute_product_attribute_ids(self):
        """Compute product attributes from attribute lines for searchpanel filtering"""
        for product in self:
            product.product_attribute_ids = product.attribute_line_ids.mapped('attribute_id')

    def _compute_dashboard_data(self):
        for product in self:
            # Revenue: "invoice value of the product for that selected product PRICE SUMMATION"
            # We take all POSTED Customer Invoices for this product.
            domain_rev = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('parent_state', '=', 'posted'),
                ('move_type', '=', 'out_invoice')
            ]
            invoice_lines = self.env['account.move.line'].search(domain_rev)
            revenue = sum(line.price_subtotal for line in invoice_lines)
            
            # Cost: "ALL EXPENCES value of the product for that selected product PRICE SUMMATION"
            # We take all POSTED Vendor Bills (Expenses) for this product.
            domain_cost = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('parent_state', '=', 'posted'),
                ('move_type', '=', 'in_invoice')
            ]
            bill_lines = self.env['account.move.line'].search(domain_cost)
            cost = sum(line.price_subtotal for line in bill_lines)
            
            # Profit
            profit = revenue - cost
            
            product.dashboard_revenue = revenue
            product.dashboard_cost = cost
            product.dashboard_profit = profit
            
            # Graph Data (Financial Overview)
            product.dashboard_graph_data = json.dumps([{
                'key': 'Profit',
                'values': [
                    {'label': 'Revenue', 'value': revenue},
                    {'label': 'Cost', 'value': cost},
                    {'label': 'Profit', 'value': profit}
                ]
            }])

    dashboard_rental_graph_data = fields.Text(compute='_compute_rental_dashboard_data', string='Rental Graph Data')

    def _compute_rental_dashboard_data(self):
        for product in self:
            # Real Data Aggregation: Daily Ordered Qty by Rental Status
            # Fetches rental lines for this specific product.
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('is_rental', '=', True),
                ('state', 'in', ['draft', 'sent', 'sale', 'done'])
            ]
            
            # Fetch records directly
            # We don't filter by start_date in SQL to avoid issues if it's not stored or empty.
            rental_lines = self.env['sale.order.line'].search(domain)
            
            # Organize data for the graph widget
            data_by_status = {}
            all_dates = set()
            
            for line in rental_lines:
                status = line.rental_status or 'undefined'
                
                # Determine date: Use start_date (rental start) or fallback to order date
                date_val = line.start_date or line.order_id.date_order
                if not date_val:
                    continue
                    
                # Format date
                if isinstance(date_val, (datetime,)):
                    date_val = date_val.date()
                date_label = date_val.strftime('%d %b %Y')
                
                qty = line.product_uom_qty
                
                if status not in data_by_status:
                    data_by_status[status] = {}
                
                # Accumulate quantities
                current_qty = data_by_status[status].get(date_label, 0.0)
                data_by_status[status][date_label] = current_qty + qty
                
                all_dates.add(date_label)
            
            # Sort dates
            # Helper to parse date string back to date object for sorting
            def parse_date_label(label):
                try:
                    return datetime.strptime(label, '%d %b %Y').date()
                except ValueError:
                    return date.min

            unique_dates_list = sorted(list(all_dates), key=parse_date_label)

            graph_data = []
            status_map = {
                'draft': {'label': 'Quotation', 'color': '#17a2b8'},      # Info/Blue
                'sent': {'label': 'Sent', 'color': '#17a2b8'},           # Info/Blue
                'pickup': {'label': 'Reserved', 'color': '#ffc107'},     # Warning/Yellow
                'return': {'label': 'Picked Up', 'color': '#fd7e14'},    # Orange
                'returned': {'label': 'Returned', 'color': '#28a745'},   # Success/Green
                'cancel': {'label': 'Cancelled', 'color': '#dc3545'},    # Danger/Red
                'undefined': {'label': 'Undefined', 'color': '#6c757d'}  # Secondary/Gray
            }

            for status, date_values in data_by_status.items():
                values_list = []
                for date_str in unique_dates_list:
                    values_list.append({
                        'label': date_str,
                        'value': date_values.get(date_str, 0.0)
                    })
                
                color = status_map.get(status, {}).get('color', '#6c757d')
                
                graph_data.append({
                    'key': status_map.get(status, {}).get('label', status.capitalize()),
                    'values': values_list,
                    'color': color,
                    'type': 'bar'
                })
            
            # If no data, return default empty structure
            if not graph_data:
                graph_data = [{'key': 'No Data', 'values': []}]
                
            product.dashboard_rental_graph_data = json.dumps(graph_data)

    def action_open_rental_analysis(self):
        """Redirect to the Rental Reporting view filtered by this product"""
        self.ensure_one()
        action = self.env["ir.actions.actions"]._for_xml_id("sales_catalog_dashboard.action_rental_reporting")
        action['name'] = f"Rental Analysis - {self.name}"
        action['domain'] = [
            ('product_id.product_tmpl_id', '=', self.id),
            ('is_rental', '=', True),
            ('state', 'in', ['sale', 'done'])
        ]
        return action

    def action_field_visit(self):
        """Open a new Field Visit (Project Task) form pre-filled with this product"""
        self.ensure_one()
        return {
            'name': 'Field Visit',
            'type': 'ir.actions.act_window',
            'res_model': 'project.task',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': f'Field Visit: {self.name}',
                'default_partner_id': self.current_owner_id.id,
                'default_sale_line_id': self.env['sale.order.line'].search([
                        ('product_id.product_tmpl_id', '=', self.id),
                        ('state', 'in', ['sale', 'done']),
                        ('is_rental', '=', True)
                    ], limit=1).id,
                'default_description': f'Field Visit for Product: {self.name}'
            }
        }
        
    def action_help_desk(self):
        """Open a new Helpdesk Ticket form pre-filled with this product"""
        self.ensure_one()
        return {
            'name': 'Help Desk',
            'type': 'ir.actions.act_window',
            'res_model': 'helpdesk.ticket',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': f'Support Request: {self.name}',
                'default_partner_id': self.current_owner_id.id,
                'default_product_id': self.product_variant_id.id,
                'default_description': f'Issue reported for Product: {self.name}'
            }
        }

    def action_maintain(self):
        """Open a new Maintenance Request form pre-filled with this product"""
        self.ensure_one()
        return {
            'name': 'Maintenance Request',
            'type': 'ir.actions.act_window',
            'res_model': 'maintenance.request',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_name': f'Maintenance Request for {self.name}',
                'default_partner_id': self.current_owner_id.id,
                'default_description': f'Maintenance requested for Product: {self.name}',
                'default_product_id': self.product_variant_id.id, 
            }
        }
    
    def action_check_in(self):
        """
        Trigger the Pickup action for the most relevant active rental booking (state='sale', rental_status='pickup').
        If multiple exist, prefer the one with the latest start_date, then creation date.
        """
        self.ensure_one()
        
        # 1. Find relevant rental line
        # We look for lines of this product that are in 'pickup' status (booked/reserved)
        # 'booking' state in requirement corresponds to rental_status='pickup' on the order line.
        domain = [
            ('product_id.product_tmpl_id', '=', self.id),
            ('is_rental', '=', True),
            ('state', '=', 'sale'),
            ('rental_status', '=', 'pickup'),
        ]
        # Order by start_date desc (latest booking) then create_date desc
        rental_line = self.env['sale.order.line'].search(domain, order='start_date desc, create_date desc', limit=1)

        if not rental_line:
            raise UserError(_("No booking rental found for this product. Please create/confirm a booking first."))

        # 2. Trigger the Pickup action on the order
        # Requirement: "Automatically trigger the same action as clicking the “Pickup” button on that Rental form."
        return rental_line.order_id.action_open_pickup()

    def action_check_out(self):
        """
        Trigger the Return action for the most relevant active rental booking (status='return').
        If multiple exist, prefer the one with the latest start_date, then creation date.
        """
        self.ensure_one()
        
        # 1. Find relevant rental line
        # We look for lines of this product that are in 'return' status (picked up)
        domain = [
            ('product_id.product_tmpl_id', '=', self.id),
            ('is_rental', '=', True),
            ('state', 'in', ['sale', 'done']),
            ('rental_status', '=', 'return'),
        ]
        # Order by start_date desc (latest booking) then create_date desc
        rental_line = self.env['sale.order.line'].search(domain, order='start_date desc, create_date desc', limit=1)

        if not rental_line:
            raise UserError(_("No picked-up rental found for this product. Please pickup/confirm a rental first."))

        # 2. Trigger the Return action on the order
        return rental_line.order_id.action_open_return()

    def action_sign_agreement(self):
        pass

    def action_asset_allocations(self):
        pass

    def action_parking_allocations(self):
        pass

    def action_open_documents(self):
        self.ensure_one()
        return {
            'name': 'Documents',
            'type': 'ir.actions.act_window',
            'res_model': 'documents.document',
            'view_mode': 'kanban,list,form',
            'domain': [('res_model', '=', 'product.template'), ('res_id', '=', self.id)],
            'context': {'default_res_model': 'product.template', 'default_res_id': self.id},
        }

    def action_open_product_profile(self):
        """Open the standard product template form view"""
        self.ensure_one()
        return {
            'name': 'Product Profile',
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': self.env.ref('product.product_template_only_form_view').id,
            'target': 'current',
        }

    def action_open_website_url(self):
        """Open the product's website URL"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': self.website_url,
            'target': 'new',
        }

    def action_view_rental_schedule(self):
        """View rental schedule for this product"""
        self.ensure_one()
        return {
            'name': 'Schedule',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'gantt,list,form',
            'domain': [('product_id.product_tmpl_id', '=', self.id), ('is_rental', '=', True)],
            'context': {
                'search_default_product_id': self.product_variant_id.id, 
                'default_product_id': self.product_variant_id.id,
                'in_rental_app': 1,
                'in_rental_schedule': 1,
            },
        }

    def action_view_rental_calendar(self):
        """View rental calendar for this product"""
        self.ensure_one()
        # Redirect to the rental calendar view
        return {
            'name': 'Calendar',
            'type': 'ir.actions.act_window',
            'res_model': 'sale.order.line',
            'view_mode': 'calendar,list,form',
            'domain': [('product_id.product_tmpl_id', '=', self.id), ('is_rental', '=', True)],
            'context': {'default_product_id': self.product_variant_id.id, 'default_is_rental': True},
        }

    def _compute_active_rental_data(self):
        today = fields.Date.context_today(self)
        for product in self:
            # Find the active rental line for today
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('is_rental', '=', True),
                ('state', 'in', ['sale', 'done']),
                ('rental_status', 'in', ['pickup', 'return']),
                ('start_date', '<=', today),
                ('return_date', '>=', today)
            ]
            # Use search to get the record
            active_rental_line = self.env['sale.order.line'].search(domain, limit=1)
            
            if active_rental_line:
                product.last_sale_order_name = active_rental_line.order_id.name
                product.current_owner_id = active_rental_line.order_partner_id
            else:
                product.last_sale_order_name = False
                product.current_owner_id = False

    def _compute_is_booked_today(self):
        today = fields.Date.context_today(self)
        for product in self:
            # Check for any rental line that covers today
            # Status: cancel, draft, sent -> Not booked. 
            # pickup (reserved), return (picked up) -> Booked.
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('is_rental', '=', True),
                ('state', 'in', ['sale', 'done']),
                ('rental_status', 'in', ['pickup', 'return']),
                ('start_date', '<=', today),
                ('return_date', '>=', today)
            ]
            booked_count = self.env['sale.order.line'].search_count(domain)
            product.is_booked_today = bool(booked_count)



    def _compute_product_payments(self):
        for product in self:
            # 1. Find all posted customer invoices for this product
            invoice_lines = self.env['account.move.line'].search([
                ('product_id.product_tmpl_id', '=', product.id),
                ('parent_state', '=', 'posted'),
                ('move_type', '=', 'out_invoice')
            ])
            invoices = invoice_lines.mapped('move_id')
            
            # 2. Find payments reconciled with these invoices
            if invoices:
                # 'reconciled_invoice_ids' is the standard Many2many on account.payment
                payments = self.env['account.payment'].search([
                    ('reconciled_invoice_ids', 'in', invoices.ids)
                ])
                product.product_payment_ids = payments
            else:
                product.product_payment_ids = False

    def _compute_product_rental_history(self):
        for product in self:
            # Fetch all rental lines for this product that are confirmed/done
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('is_rental', '=', True),
                ('state', 'in', ['sale', 'done'])
            ]
            rental_lines = self.env['sale.order.line'].search(domain, order='start_date desc')
            product.product_rental_history_ids = rental_lines

    def _compute_product_maintenance_history(self):
        for product in self:
            # Fetch maintenance requests linked to this product (via equipment or directly if customized)
            # Standard maintenance links to equipment. Equipment links to product.
            # Fetch maintenance requests linked to this product (via equipment or directly)
            requests = self.env['maintenance.request'].search([
                '|',
                ('equipment_id.product_id.product_tmpl_id', '=', product.id),
                ('product_id.product_tmpl_id', '=', product.id)
            ])
            product.product_maintenance_ids = requests

    def _compute_product_invoice_history(self):
        for product in self:
            # Fetch invoice lines for this product (Customer Invoices)
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('parent_state', '=', 'posted'),
                ('move_type', '=', 'out_invoice')
            ]
            invoice_lines = self.env['account.move.line'].search(domain, order='date desc')
            product.product_invoice_ids = invoice_lines

    def _compute_product_sale_history(self):
        for product in self:
            # Fetch Sales Order Lines (excluding rentals)
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('state', 'in', ['sale', 'done']),
                ('is_rental', '=', False)
            ]
            sale_lines = self.env['sale.order.line'].search(domain, order='order_id desc')
            product.product_sale_order_ids = sale_lines

    def _compute_product_vendor_bill_history(self):
        for product in self:
            # Fetch Vendor Bill Lines
            domain = [
                ('product_id.product_tmpl_id', '=', product.id),
                ('parent_state', '=', 'posted'),
                ('move_type', '=', 'in_invoice')
            ]
            bill_lines = self.env['account.move.line'].search(domain, order='date desc')
            product.product_vendor_bill_ids = bill_lines

class SalesCatalogSection(models.Model):
    _name = 'sales.catalog.section'
    _description = 'Sales Catalog Section'
    _order = 'name'

    name = fields.Char(required=True)

