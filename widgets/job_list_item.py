"""Widget showing a single stacking or upload job with progress."""

from kivy.uix.boxlayout import BoxLayout
from kivy.properties import StringProperty, NumericProperty


class JobListItem(BoxLayout):
    job_id = StringProperty("")
    source_label = StringProperty("")    # IP for seestar, dir path for harddrive
    target_name = StringProperty("")
    chunk_time = StringProperty("")
    status = StringProperty("pending")   # pending | running | complete | failed
    progress = NumericProperty(0)        # 0-100
    phase_text = StringProperty("")      # "loading", "aligning", etc. (local mode)
