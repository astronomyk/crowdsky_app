"""CrowdSky App v3 — main entry point.

Launch: ``python main.py`` (or ``python -m crowdsky_app``).
"""

import os
import sys
import types

# ---------------------------------------------------------------------------
# Bootstrap: make 'crowdsky_app' importable in every runtime context.
#
#   Desktop (source):   parent dir added to sys.path -> package found naturally.
#   PyInstaller:        _MEIPASS contains crowdsky_app/ sub-directory.
#   Android / Buildozer: main.py is at app root; files live *beside* it, not
#                        inside a crowdsky_app/ sub-dir.  We register a
#                        virtual package whose __path__ is the app directory
#                        so that ``from crowdsky_app.xxx import ...`` works.
# ---------------------------------------------------------------------------
if getattr(sys, 'frozen', False):
    # Running as PyInstaller bundle
    _APP_DIR = os.path.join(sys._MEIPASS, 'crowdsky_app')
    sys.path.insert(0, sys._MEIPASS)
elif 'ANDROID_ARGUMENT' in os.environ:
    # Running on Android via python-for-android / Buildozer
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    if 'crowdsky_app' not in sys.modules:
        _pkg = types.ModuleType('crowdsky_app')
        _pkg.__path__ = [_APP_DIR]
        _pkg.__file__ = os.path.join(_APP_DIR, '__init__.py')
        _pkg.__package__ = 'crowdsky_app'
        sys.modules['crowdsky_app'] = _pkg
else:
    _APP_DIR = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(_APP_DIR))

from kivy.config import Config
Config.set('graphics', 'width', '390')
Config.set('graphics', 'height', '844')

from kivy.app import App
from kivy.factory import Factory
from kivy.uix.screenmanager import ScreenManager, SlideTransition

_IS_ANDROID = 'ANDROID_ARGUMENT' in os.environ

from crowdsky_app.widgets.filter_bar import FilterBar
from crowdsky_app.widgets.gallery_card import GalleryCard
from crowdsky_app.widgets.pagination_bar import PaginationBar
from crowdsky_app.widgets.sky_map import SkyMapWidget
from crowdsky_app.widgets.timeline import TimelineWidget
from crowdsky_app.widgets.album_row import AlbumRow
from crowdsky_app.widgets.donate_seestar_card import DonateSeestarCard
from crowdsky_app.widgets.job_list_item import JobListItem
from crowdsky_app.widgets.horizon_compass import HorizonCompass
from crowdsky_app.widgets.plan_skymap import PlanSkyMap
from crowdsky_app.screens.login_screen import LoginScreen
from crowdsky_app.screens.home_screen import HomeScreen
from crowdsky_app.screens.skymap_screen import SkyMapScreen
from crowdsky_app.screens.gallery_screen import GalleryScreen
from crowdsky_app.screens.donate_seestar_screen import DonateSeestarScreen
from crowdsky_app.screens.plan_screen import PlanScreen
from crowdsky_app.screens.status_screen import StatusScreen

if not _IS_ANDROID:
    from crowdsky_app.widgets.donate_harddrive_card import DonateHarddriveCard
    from crowdsky_app.screens.donate_harddrive_screen import DonateHarddriveScreen

# Register custom widgets so KV language can reference them
Factory.register("FilterBar", cls=FilterBar)
Factory.register("GalleryCard", cls=GalleryCard)
Factory.register("PaginationBar", cls=PaginationBar)
Factory.register("SkyMapWidget", cls=SkyMapWidget)
Factory.register("TimelineWidget", cls=TimelineWidget)
Factory.register("AlbumRow", cls=AlbumRow)
Factory.register("DonateSeestarCard", cls=DonateSeestarCard)
Factory.register("JobListItem", cls=JobListItem)
Factory.register("HorizonCompass", cls=HorizonCompass)
Factory.register("PlanSkyMap", cls=PlanSkyMap)

if not _IS_ANDROID:
    Factory.register("DonateHarddriveCard", cls=DonateHarddriveCard)


class CrowdSkyApp(App):
    title = "CrowdSky"
    kv_directory = _APP_DIR

    def build(self):
        sm = ScreenManager(transition=SlideTransition())
        sm.add_widget(LoginScreen(name="login"))
        sm.add_widget(HomeScreen(name="home"))
        sm.add_widget(SkyMapScreen(name="skymap"))
        sm.add_widget(GalleryScreen(name="gallery"))
        sm.add_widget(DonateSeestarScreen(name="donate_seestar"))
        if not _IS_ANDROID:
            sm.add_widget(DonateHarddriveScreen(name="donate_harddrive"))
        sm.add_widget(PlanScreen(name="plan"))
        sm.add_widget(StatusScreen(name="status"))
        return sm


def main():
    CrowdSkyApp().run()


if __name__ == "__main__":
    main()
