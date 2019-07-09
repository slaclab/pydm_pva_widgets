from pydm.widgets.qtplugin_base import qtplugin_factory
from pydm.widgets.qtplugin_extensions import (ChannelExtension, RulesExtension)

from .widgets import NTTable, NTImage

BASE_EXTENSIONS = [ChannelExtension, RulesExtension]

GROUP_NAME = "PyDM PVAccess"

NTTablePlugin = qtplugin_factory(NTTable, group=GROUP_NAME,
                                 extensions=BASE_EXTENSIONS)

NTImagePlugin = qtplugin_factory(NTImage, group=GROUP_NAME,
                                 extensions=BASE_EXTENSIONS)
