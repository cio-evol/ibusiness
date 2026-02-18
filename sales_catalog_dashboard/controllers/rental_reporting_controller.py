# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http
from odoo.http import request
import json


class RentalReportingController(http.Controller):

    @http.route('/sales_catalog_dashboard/rental_reporting/chart_data', type='json', auth='user')
    def get_chart_data(self, product_id=None, date_from=None, date_to=None, **kwargs):
        """
        Returns JSON data for live graph based on selected product
        Data includes: time-series rental data and profit/utilization/status breakdown
        """
        if not product_id:
            return {'error': 'No product selected'}
        
        product = request.env['product.product'].browse(product_id)
        if not product.exists():
            return {'error': 'Product not found'}
        
        # Get aggregated data from model with date range
        chart_data = request.env['sale.rental.report'].get_product_chart_data(
            product_id, 
            date_from=date_from, 
            date_to=date_to
        )
        
        return chart_data

