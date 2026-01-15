{
    'name': 'Morocco Regional Access',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Gestion géographique des clients et sécurité par région',
    'description': """
        Ce module permet de :
        - Structurer les clients par régions et villes du Maroc
        - Restreindre l'accès aux clients selon les régions affectées à chaque utilisateur
    """,
    'author': 'Rida Louchachha <ridalouchachha2580@gmail.com>',
    'depends': ['base', 'contacts', 'sale', 'sale_subscription'],
    'data': [
        'security/ir.model.access.csv',
        'security/security.xml',
        'data/res_region_ma_data.xml',
        'data/res_city_ma_data.xml',
        'views/res_region_ma_views.xml',
        'views/ma_system_version_views.xml',
        'views/res_city_ma_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
        'views/sale_order_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
