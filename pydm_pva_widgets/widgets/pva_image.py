import logging

import numpy as np
from pydm.widgets.base import PyDMWidget
from pydm.widgets.colormaps import cmaps, cmap_names, PyDMColorMap
from qtpy import QtCore, QtGui, QtWidgets, QtOpenGL

logger = logging.getLogger(__name__)


class NTImageUpdateThread(QtCore.QThread):
    updateSignal = QtCore.Signal()

    def __init__(self, widget):
        QtCore.QThread.__init__(self)
        self.widget = widget

    def run(self):
        data = self.widget._data
        needs_redraw = self.widget._needs_redraw

        if data is None:
            logging.debug("NTImageUpdateThread - Image was None. Aborting.")
            return

        if not needs_redraw:
            logging.debug(
                "NTImageUpdateThread - needs redraw is False. Aborting.")
            return

        try:
            image = data['value']
            color_mode = data['attribute'][0]['value']
        except (KeyError, IndexError):
            logging.debug("NTImageUpdateThread - Failed to fetch color mode.")
            return

        shape = image.shape
        if color_mode == 0:  # Mono
            w, h = shape[0], shape[1]
            format = QtGui.QImage.Format_Indexed8
        elif color_mode == 2:  # RGB1
            w, h = shape[1], shape[2]
            image.shape = (w, h, 3)
            format = QtGui.QImage.Format_RGB888
        elif color_mode == 3:  # RGB2
            w, h = shape[0], shape[2]
            image.shape = (w, 3, h)
            image = image.swapaxes(1, 2)
            format = QtGui.QImage.Format_RGB888
        elif color_mode == 4:  # RGB3
            w, h = shape[0], shape[1]
            image.shape = (3, w, h)
            image = image.swapaxes(0, 2)
            format = QtGui.QImage.Format_RGB888
        else:
            logging.debug(
                "NTImageUpdateThread - ColorMode {} is not supported.".format(
                    color_mode))
            return

        data['value'] = image
        # TODO: Call process_data here.
        data = self.widget.process_image(data)
        # Fetch again the new image after processing
        image = data['value']

        # Interpolate values to be in range 0-255.x
        if image.dtype != np.uint8:
            min = 0
            max = np.iinfo(image.dtype).max
            image = np.interp(image, (min, max), (0, 255)).astype(np.uint8)

        qimage = QtGui.QImage(image.copy(), w, h, format)

        # Apply LUT only to Mono images
        if color_mode == 0 and self.widget._colormap:
            qimage.setColorTable(self.widget._colormap)
            qimage = qimage.convertToFormat(QtGui.QImage.Format_RGB888)

        scene = self.widget.scene
        if scene.width() != w or scene.height() != h:
            qimage = qimage.scaled(scene.width(), scene.height(),
                                   QtCore.Qt.KeepAspectRatio)

        self.widget._image = qimage
        logging.debug("NTImageUpdateThread - Emit Update Signal")
        self.updateSignal.emit()
        logging.debug("NTImageUpdateThread - Set Needs Redraw -> False")
        self.widget._needs_redraw = False


class NTImage(QtWidgets.QWidget, PyDMWidget):
    color_maps = cmaps

    def __init__(self, parent=None, init_channel=None):
        super(NTImage, self).__init__(parent=parent, init_channel=init_channel)

        self.setLayout(QtWidgets.QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.scene = QtWidgets.QGraphicsScene(self)
        self.scene.setBackgroundBrush(QtGui.QColor("black"))

        self.pixmap_image = QtWidgets.QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_image)

        self.view = QtWidgets.QGraphicsView(self)
        self.view.setViewport(QtOpenGL.QGLWidget(QtOpenGL.QGLFormat()))
        self.view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.view.viewport().setContentsMargins(0, 0, 0, 0)
        self.view.setContentsMargins(0, 0, 0, 0)
        size_policy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                            QtWidgets.QSizePolicy.Preferred)
        size_policy.setHeightForWidth(True)
        self.view.setSizePolicy(size_policy)

        self.view.setScene(self.scene)

        self.layout().addWidget(self.view)

        # Make a right-click menu for changing the color map.
        self.cm_group = QtWidgets.QActionGroup(self)
        self.cmap_for_action = {}
        for cm in self.color_maps:
            action = self.cm_group.addAction(cmap_names[cm])
            action.setCheckable(True)
            self.cmap_for_action[action] = cm

        self.thread = None
        self._colormap = None
        self._data = None
        self._image = None

        # Setup the redraw timer.
        self._needs_redraw = False
        self._make_colormap(cmaps[PyDMColorMap.Monochrome])
        self._redraw_timer = QtCore.QTimer()
        self._redraw_timer.timeout.connect(self._redraw)
        self._redraw_rate = 30
        self.maxRedrawRate = self._redraw_rate
        self._redraw_timer.start()

    def widget_ctx_menu(self):
        """
        Fetch the Widget specific context menu.

        It will be populated with additional tools by `assemble_tools_menu`.

        Returns
        -------
        QMenu or None
            If the return of this method is None a new QMenu will be created by
            `assemble_tools_menu`.
        """
        self.menu = QtWidgets.QMenu(parent=self)
        cm_menu = self.menu.addMenu("Color Map")
        for act in self.cmap_for_action.keys():
            cm_menu.addAction(act)
        cm_menu.triggered.connect(self._changeColorMap)
        return self.menu

    def _changeColorMap(self, action):
        """
        Method invoked by the colormap Action Menu.

        Changes the current colormap used to render the image.

        Parameters
        ----------
        action : QAction
        """
        cmap = self.color_maps[self.cmap_for_action[action]]
        self._make_colormap(cmap)

    def _make_colormap(self, cmap, update=True):
        table = []

        for entry in cmap:
            c = QtGui.QColor()
            try:
                alpha = entry[3]
            except IndexError:
                alpha = 1
            c.setRgbF(entry[0], entry[1], entry[2], alpha)
            table.append(c.rgb())

        if len(table) != 0:
            self._colormap = table
        else:
            self._colormap = None

        if update and self._image is not None and self._colormap:
            self._image.setColorTable(self._colormap)

    def generate_context_menu(self):
        """
        Generates the custom context menu, and populates it with any external
        tools that have been loaded.  PyDMWidget subclasses should override
        this method (after calling superclass implementation) to add the menu.

        Returns
        -------
        QMenu
        """
        menu = self.widget_ctx_menu()
        if menu is None:
            menu = QtWidgets.QMenu(parent=self)
        return menu

    def open_context_menu(self, ev):
        """
        Handler for when the Default Context Menu is requested.

        Parameters
        ----------
        ev : QEvent
        """
        menu = self.generate_context_menu()
        menu.exec_(self.mapToGlobal(ev.pos()))
        menu.deleteLater()
        del menu

    def resizeEvent(self, resize_event):
        super(NTImage, self).resizeEvent(resize_event)
        w = self.view.width()
        h = self.view.height()

        size = min(w, h)
        self.scene.setSceneRect(0, 0, size, size)
        # self.receive(self._data)

    def _receive_data(self, data=None, introspection=None, *args, **kwargs):
        super(NTImage, self)._receive_data(data, introspection, *args,
                                           **kwargs)
        if data is None:
            return
        self._data = data
        self._needs_redraw = True

    def process_image(self, data):
        """
        Boilerplate method to be used by applications in order to
        add calculations and also modify the image before it is
        displayed at the widget.

        .. warning::
           This code runs in a separated QThread so it **MUST** not try to
           write to QWidgets.

        Parameters
        ----------
        data : dict
            A dictionary with the contents of the NTNDArray.
            The image can be fetched with data['value'].

        Returns
        -------
        dict
            The updated dict after processing
        """
        return data

    def _redraw(self):
        """
        Set the image data into the ImageItem, if needed.

        If necessary, reshape the image to 2D first.
        """
        if self.thread is not None and not self.thread.isFinished():
            logger.warning(
                "NTImage processing has taken longer than the refresh rate.")
            return
        self.thread = NTImageUpdateThread(self)
        self.thread.updateSignal.connect(self.__update_display)
        logging.debug("NTImageView RedrawImage Thread Launched")
        self.thread.start()

    @QtCore.Slot()
    def __update_display(self):
        self.pixmap_image.setPixmap(QtGui.QPixmap.fromImage(self._image))

    @QtCore.Property(int)
    def maxRedrawRate(self):
        """
        The maximum rate (in Hz) at which the plot will be redrawn.

        The plot will not be redrawn if there is not new data to draw.

        Returns
        -------
        int
        """
        return self._redraw_rate

    @maxRedrawRate.setter
    def maxRedrawRate(self, redraw_rate):
        """
        The maximum rate (in Hz) at which the plot will be redrawn.

        The plot will not be redrawn if there is not new data to draw.

        Parameters
        -------
        redraw_rate : int
        """
        self._redraw_rate = redraw_rate
        self._redraw_timer.setInterval(int((1.0 / self._redraw_rate) * 1000))
