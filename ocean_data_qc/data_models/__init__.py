# -*- coding: utf-8 -*-
#########################################################################
#    License, authors, contributors and copyright information at:       #
#    AUTHORS and LICENSE files at the root folder of this application   #
#########################################################################

# def joke():
#     return (u'Wenn ist das Nunst\u00fcck git und Slotermeyer? Ja! ... '
#             u'Beiherhund das Oder die Flipperwaldt gersput.')

from ocean_data_qc.data_models.cruise_data_handler import CruiseDataHandler
from ocean_data_qc.data_models.electron_bokeh_bridge import ElectronBokehBridge
from ocean_data_qc.data_models.files_handler import FilesHandler
from ocean_data_qc.data_models.octave_equations import OctaveEquations

CruiseDataHandler()
FilesHandler()
OctaveEquations()
ElectronBokehBridge()

