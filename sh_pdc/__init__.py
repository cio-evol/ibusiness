# -*- coding: utf-8 -*-
# Part of Softhealer Technologies.
from . import models
from . import wizard



def post_init_hook(env):
    # Update old customers and vendors.
    account_obj = env['account.account']
    for company in env['res.company'].sudo().search([]):
        domain_customer = [('name', '=', 'PDC Receivable'), ('company_ids', 'in', [company.id])]
        domain_vendor = [('name', '=', 'PDC Payable'), ('company_ids', 'in', [company.id])]
        company.write({
            'pdc_customer': account_obj.sudo().search(domain_customer, limit=1).id or False,
            'pdc_vendor': account_obj.sudo().search(domain_vendor, limit=1).id or False,
        })
