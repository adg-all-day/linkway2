from django.db import migrations


def create_default_categories(apps, schema_editor):
  ProductCategory = apps.get_model("products", "ProductCategory")

  defaults = [
      ("Electronics", "electronics"),
      ("Fashion", "fashion"),
      ("Beauty & Personal Care", "beauty-personal-care"),
      ("Home & Living", "home-living"),
      ("Sports & Fitness", "sports-fitness"),
      ("Digital Products", "digital-products"),
      ("Online Courses", "online-courses"),
      ("Ebooks", "ebooks"),
      ("Software & Apps", "software-apps"),
      ("Services", "services"),
      ("Others", "others"),
  ]

  for name, slug in defaults:
      ProductCategory.objects.get_or_create(slug=slug, defaults={"name": name})


class Migration(migrations.Migration):
  dependencies = [
      ("products", "0001_initial"),
  ]

  operations = [
      migrations.RunPython(create_default_categories, migrations.RunPython.noop),
  ]

