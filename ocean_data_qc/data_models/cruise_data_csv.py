# -*- coding: utf-8 -*-
#########################################################################
#    License, authors, contributors and copyright information at:       #
#    AUTHORS and LICENSE files at the root folder of this application   #
#########################################################################

from bokeh.util.logconfig import bokeh_logger as lg
from ocean_data_qc.constants import *
from ocean_data_qc.data_models.cruise_data_parent import CruiseDataParent
from ocean_data_qc.data_models.exceptions import ValidationError
from ocean_data_qc.env import Environment

import csv


class CruiseDataCSV(CruiseDataParent):
    ''' This class is used to manage the plain CSV files (non-WHP format)
    '''
    env = CruiseDataParent.env

    def __init__(self):
        lg.warning('-- INIT CSV')
        self.filepath_or_buffer = ORIGINAL_CSV
        self.skiprows = 0
        super(CruiseDataCSV, self).__init__(original_type='csv')

    def _validate_original_data(self):
        ''' Checks if all the rows have the same number of elements '''
        lg.warning('-- CHECK DATA FORMAT (CSV)')
        with open(ORIGINAL_CSV, newline='') as csvfile:
            spamreader = csv.reader(csvfile, delimiter=',', quotechar='"')
            first_len = -1
            row_number = 1
            for row in spamreader:
                row_number += 1
                if first_len == -1:
                    first_len = len(row)
                else:
                    if first_len != len(row):
                        csvfile.close()
                        raise ValidationError(
                            'There is an invalid number of fields ({}) in the row: {}.'
                            ' The number of header columns fields is: {}'.format(
                                len(row), row_number, first_len
                            ),
                            rollback='cruise_data'
                        )
                        break                               # interrupt for loop

    def load_file(self):
        lg.warning('-- LOAD FILE CSV (cruise_data_aqc)')
        self._set_moves()
        self._load_from_scratch()