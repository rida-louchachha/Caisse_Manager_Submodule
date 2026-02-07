from odoo.tests import common, tagged
from odoo.fields import Date

@tagged('post_install', '-at_install')
class TestRevenueAnalysis(common.TransactionCase):

    def setUp(self):
        super(TestRevenueAnalysis, self).setUp()
        
        # Setup Hierarchy
        self.client = self.env['res.partner'].create({'name': 'Client 1', 'partner_level': 'client'})
        self.franchise = self.env['res.partner'].create({'name': 'Franchise 1', 'partner_level': 'franchise', 'parent_id': self.client.id})
        self.company = self.env['res.partner'].create({'name': 'Store 1', 'partner_level': 'company', 'parent_id': self.franchise.id})
        
        # Create Product
        self.product = self.env['product.product'].create({'name': 'Test Product', 'list_price': 100.0})
        self.sub_product = self.env['product.product'].create({'name': 'Sub Product', 'list_price': 50.0, 'recurring_invoice': True})

    def test_01_revenue_aggregation(self):
        """Test if revenue is correctly aggregated in the SQL view."""
        
        # 1. Create Standard Sale Order
        so1 = self.env['sale.order'].create({
            'partner_id': self.company.id,
            'date_order': Date.today(),
        })
        self.env['sale.order.line'].create({
            'order_id': so1.id,
            'product_id': self.product.id,
        })
        so1.action_confirm()

        # 2. Create Subscription Order (Simulated via is_subscription_revenue flag or recurring product)
        # Note: Depending on Odoo version, `sale_subscription` logic varies. 
        # Assuming our `is_subscription_revenue` compute or manual set.
        so2 = self.env['sale.order'].create({
            'partner_id': self.company.id,
            'date_order': Date.today(),
            'is_subscription': True, # Explicitly setting for test if possible, or rely on product
        })
        self.env['sale.order.line'].create({
            'order_id': so2.id,
            'product_id': self.sub_product.id,
        })
        so2.action_confirm()
        
        # Refresh View
        self.env.cr.execute("REFRESH MATERIALIZED VIEW cm_revenue_analysis") if 'MATERIALIZED' in str(self.env['cm.revenue.analysis']._table) else None
        
        # Query View
        analysis = self.env['cm.revenue.analysis'].search([('partner_id', '=', self.company.id)])
        
        # Assertions
        # Note: We group by everything, so we might have 1 line if dates match, or 2 if something differs.
        # Assuming same month/year
        
        total_revenue = sum(analysis.mapped('total_revenue'))
        sub_revenue = sum(analysis.mapped('subscription_revenue'))
        non_sub_revenue = sum(analysis.mapped('non_subscription_revenue'))
        
        self.assertEqual(total_revenue, 150.0, "Total revenue should be 150")
        self.assertEqual(sub_revenue, 50.0, "Subscription revenue should be 50")
        self.assertEqual(non_sub_revenue, 100.0, "Non-subscription revenue should be 100")
        
        # Check Hierarchy Grouping (Client Level)
        client_analysis = self.env['cm.revenue.analysis'].search([('client_id', '=', self.client.id)])
        self.assertTrue(len(client_analysis) > 0, "Should find records at client level")
        self.assertEqual(sum(client_analysis.mapped('total_revenue')), 150.0, "Client total revenue should match")

