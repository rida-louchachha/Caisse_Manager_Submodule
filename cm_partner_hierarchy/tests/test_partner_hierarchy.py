from odoo.tests import common, tagged

@tagged('post_install', '-at_install')
class TestPartnerHierarchy(common.TransactionCase):

    def setUp(self):
        super(TestPartnerHierarchy, self).setUp()
        
        # Create Client
        self.client_partner = self.env['res.partner'].create({
            'name': 'Test Client',
            'partner_level': 'client',
        })
        
        # Create Franchise
        self.franchise_partner = self.env['res.partner'].create({
            'name': 'Test Franchise',
            'parent_id': self.client_partner.id,
            'partner_level': 'franchise',
        })
        
        # Create Company (Store)
        self.company_partner = self.env['res.partner'].create({
            'name': 'Test Store',
            'parent_id': self.franchise_partner.id,
            'partner_level': 'company',
        })
        
        # Create Unclassified Partner attached to Client
        self.unclassified_partner = self.env['res.partner'].create({
            'name': 'Unclassified Partner',
            'parent_id': self.client_partner.id,
        })

    def test_01_hierarchy_computation(self):
        """Test if client_id and franchise_id are correctly computed."""
        
        # Validate Client
        self.assertEqual(self.client_partner.hierarchy_client_id, self.client_partner, "Client should be its own client")
        self.assertFalse(self.client_partner.hierarchy_franchise_id, "Client should not have franchise_id")
        
        # Validate Franchise
        self.assertEqual(self.franchise_partner.hierarchy_client_id, self.client_partner, "Franchise should have correct client")
        self.assertFalse(self.franchise_partner.hierarchy_franchise_id, "Franchise should not have franchise_id (it IS the franchise)")
        
        # Validate Company/Store
        self.assertEqual(self.company_partner.hierarchy_client_id, self.client_partner, "Store should have correct client")
        self.assertEqual(self.company_partner.hierarchy_franchise_id, self.franchise_partner, "Store should have correct franchise")

    def test_02_child_counts(self):
        """Test child franchise and company counts."""
        self.assertEqual(self.client_partner.franchise_count, 1, "Client should have 1 franchise")
        self.assertEqual(self.franchise_partner.company_count, 1, "Franchise should have 1 company")
        
    def test_03_classification_server_action(self):
        """Test manually setting partner level via server action logic."""
        # Note: Server actions usually call write(), keeping it simple here
        self.unclassified_partner.action_set_as_franchise()
        self.assertEqual(self.unclassified_partner.partner_level, 'franchise', "Partner should be promoted to Franchise")
        self.assertEqual(self.unclassified_partner.hierarchy_client_id, self.client_partner, "New franchise should link to parent client")

    def test_04_partner_resume_counts(self):
        """Test computations for partner resume (sales, subscriptions)."""
        # Create a sale order
        sale = self.env['sale.order'].create({
            'partner_id': self.company_partner.id,
            'state': 'sale',
        })
        # Order count should propagate up? 
        # Actually fields are computed non-stored or stats on stored fields.
        # Let's check `sale_order_count` if we rely on standard Odoo, 
        # or if we need to check our resume wizard logic which does dynamic queries.
        
        # We'll just verify the wizard creation works
        wizard = self.env['partner.resume.wizard'].create({
            'partner_id': self.company_partner.id
        })
        self.assertEqual(wizard.total_sales, 1, "Wizard should see 1 sale order")
