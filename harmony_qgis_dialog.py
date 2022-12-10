# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HarmonyQGISDialog
                                 A QGIS plugin
 Access the Harmony service broker to process and download Earth science data
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                             -------------------
        begin                : 2020-04-05
        git sha              : $Format:%H$
        copyright            : (C) 2020 NASA
        email                : james@element84.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

# This loads your .ui file so that PyQt can populate your plugin with the elements from Qt Designer
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'harmony_qgis_dialog_base.ui'))


class HarmonyQGISDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        """Constructor."""
        super(HarmonyQGISDialog, self).__init__(parent)
        # Set up the user interface from Designer through FORM_CLASS.
        # After self.setupUi() you can access any designer object by doing
        # self.<objectname>, and you can use autoconnect slots - see
        # http://qt-project.org/doc/qt-4.8/designer-using-a-ui-file.html
        # #widgets-and-dialogs-with-auto-connect
        self.setupUi(self)

    # validate the collection, version, and variable fields 
    def validateInput(self):
        collectionId = self.collectionField.text()
        if collectionId == None or collectionId == '':
            QtWidgets.QMessageBox.information(self, "Error!", "The collection field is required" )
            return False
            
        variable = self.variableField.text()
        if variable == None or variable == '':
            QtWidgets.QMessageBox.information(self, "Error!", "The variable field is required" )
            return False
        return True
    
    # check to see if the input is valid before closing the dialog
    def accept(self):
        validInput = self.validateInput()
        if validInput:
            self.done(1)
