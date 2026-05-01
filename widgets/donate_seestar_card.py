"""Widget showing a Seestar card with album list for the donate screen."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, BooleanProperty


class DonateSeestarCard(BoxLayout):
    serial_number = StringProperty("")
    ip_address = StringProperty("")
    product_model = StringProperty("")
    is_expanded = BooleanProperty(True)
    scrub_location = BooleanProperty(False)

    def toggle_expanded(self):
        self.is_expanded = not self.is_expanded

    def select_all(self):
        for child in self.ids.album_list.children:
            if hasattr(child, "is_complete") and not child.is_complete:
                child.is_selected = True

    def deselect_all(self):
        for child in self.ids.album_list.children:
            if hasattr(child, "is_selected"):
                child.is_selected = False
