
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AccountJournal(models.Model):
    _inherit = "account.journal"

    cheque_in_hand = fields.Boolean(string="Cheque in Hand", default=False)

