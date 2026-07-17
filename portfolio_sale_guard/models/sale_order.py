from collections import defaultdict

from odoo import _, models
from odoo.exceptions import UserError, ValidationError


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _portfolio_stock_shortages(self):
        self.ensure_one()
        required = defaultdict(float)
        for line in self.order_line.filtered(lambda item: not item.display_type and item.product_id.is_storable):
            required[line.product_id] += line.product_uom._compute_quantity(line.product_uom_qty, line.product_id.uom_id)
        result = []
        for product, quantity in required.items():
            available = product.with_context(location=self.warehouse_id.lot_stock_id.id).free_qty
            if available < quantity:
                result.append((product, quantity, available))
        return result

    def action_portfolio_check_stock(self):
        self.ensure_one()
        shortages = self._portfolio_stock_shortages()
        if shortages:
            details = "\n".join(
                _("%(product)s: required %(required)s, available %(available)s")
                % {"product": p.display_name, "required": q, "available": a}
                for p, q, a in shortages
            )
            raise ValidationError(_("Insufficient stock:\n%s") % details)
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {"title": _("Stock Check"), "message": _("All required products are available."), "type": "success"}}

    def action_portfolio_complete_sale(self):
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            raise UserError(_("Only quotations can use this action."))
        self.action_portfolio_check_stock()
        self.action_confirm()
        for picking in self.picking_ids.filtered(lambda record: record.state not in ("done", "cancel")):
            picking.action_assign()
        invoices = self._create_invoices()
        return {"type": "ir.actions.act_window", "name": _("Customer Invoice"), "res_model": "account.move", "view_mode": "form", "res_id": invoices[:1].id}
