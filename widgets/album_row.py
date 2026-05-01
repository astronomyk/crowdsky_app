"""Widget showing a single target with checkbox and traffic-light counts."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, NumericProperty, BooleanProperty


class AlbumRow(BoxLayout):
    target_name = StringProperty("")
    green_count = NumericProperty(0)
    yellow_count = NumericProperty(0)
    red_count = NumericProperty(0)
    is_selected = BooleanProperty(True)
    is_complete = BooleanProperty(False)
