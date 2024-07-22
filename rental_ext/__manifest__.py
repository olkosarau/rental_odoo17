{
    "name": "Rental Extension",
    "version": "17.0.0.2",
    'description': """For adding start date and end date on renting sale order lines""",
    'category': 'Discuss',
    'author': "Codoo-ERP",
    'website': "https://codoo-erp.com/",
    'license': 'LGPL-3',
    "summary": "Adds start date and end date on renting sale order lines",
    "depends": [
        "base",
        "sale_renting",
        "sale_stock_renting",
    ],
    "data": [
        "views/sale_order.xml",
    ],
    "installable": True,
}
