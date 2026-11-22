import unittest

from validate import Page


class ProductPageParserTest(unittest.TestCase):
    def test_valueless_attributes_do_not_hide_later_product_evidence(self):
        page = Page()
        page.feed(
            '<div class></div><a href></a><link rel href><meta name="empty" content>'
            '<h1 class>Shop</h1><meta property="og:type" content="product">'
            '<link rel="canonical" href="https://example.org/product/mug">'
            '<h1 class="product_title">Travel Mug</h1>'
            '<script type="application/ld+json">{"@type":"Product"}</script>'
        )
        page.close()
        self.assertEqual(page.meta["empty"], "")
        self.assertEqual(page.meta["og:type"], "product")
        self.assertEqual(page.canonical, "https://example.org/product/mug")
        self.assertEqual(page.titles, ["Shop", "Travel Mug"])
        self.assertTrue(page.product_heading)
        self.assertEqual(page.schemas, [{"@type": "Product"}])
        self.assertFalse(page.add_to_cart)

    def test_empty_attributes_do_not_create_product_or_cart_evidence(self):
        page = Page()
        page.feed('<div class><link rel href><a href><h1 class>Shop</h1></a></div>')
        page.close()
        self.assertIsNone(page.canonical)
        self.assertFalse(page.product_heading)
        self.assertFalse(page.add_to_cart)
        self.assertFalse(page.schemas)


if __name__ == "__main__":
    unittest.main()
