# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    ejari_expiry_warning_days = fields.Integer(
        string="Ejari Expiry Warning (Days)",
        default=30,
        help="Number of days before Ejari expiry to consider it 'expiring soon' "
        "and trigger notifications.",
    )
