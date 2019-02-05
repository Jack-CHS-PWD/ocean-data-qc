# -*- coding: utf-8 -*-
#########################################################################
#    License, authors, contributors and copyright information at:       #
#    AUTHORS and LICENSE files at the root folder of this application   #
#########################################################################

from bokeh.util.logconfig import bokeh_logger as lg
from ocean_data_qc.constants import *
from ocean_data_qc.data_models.exceptions import ValidationError
from ocean_data_qc.data_models.computed_parameter import ComputedParameter
from ocean_data_qc.data_models.cruise_data_export import CruiseDataExport

import csv
import json
import os
import pandas as pd
import numpy as np
from os import path
import hashlib
from datetime import datetime
from shutil import rmtree


class CruiseData(CruiseDataExport):
    ''' This class is gathering all the common methods needed to manage
        the aqc, csv and whp files
    '''
    env = CruiseDataExport.env

    def __init__(self, original_type=''):
        lg.warning('-- INIT CRUISE DATA PARENT')
        self.env.cruise_data = self
        self.original_type = original_type
        self._validate_original_data()

        self.df = None
        self.moves = None
        self.cols = {}

        self.load_file()  # implemented in the children

    def _load_from_scratch(self):
        lg.info('-- LOAD FROM SCRATCH')
        self._set_df()
        self._set_attributes_from_scratch()  # the dataframe has to be created
        self._validate_required_columns()
        self._replace_missing_values()         # '-999' >> NaN
        self._init_early_calculated_params()
        self._convert_data_to_number()
        self._set_hash_ids()

        # TODO: confusing methods names, options:
        #       They are saved in the temporal folder instead of the aqc file
        self.save_tmp_data()

    def _load_from_files(self):
        lg.info('-- LOAD FROM FILES')
        self._set_df()
        self._set_attributes_from_json_file()
        self._replace_missing_values()         # '-999' >> NaN
        self._convert_data_to_number()
        self._set_hash_ids()

    def _set_attributes_from_scratch(self):
        """ The main attributes of the object are filled:

                "cols": {
                    "ALKALI": {
                        "types": ["param"],
                        "required": False,
                        "unit": "UMOL/KG",
                    },
                    "ALKALI_FLAG_W": {
                        "types": ["param_flag", "qc_param_flag"],
                        "required": False,
                        "unit": NaN,  # >> False
                    }
                }
        """
        lg.info('-- SET ATTRIBUTES FROM SCRATCH --')
        if self.original_type == 'whp':
            units_list = self.df.iloc[0].values.tolist()  # TODO: how to detect if there are units or not?
                                                          #       how to fill the units fields then?
        else:
            units_list = []
        pos = 0
        column_list = self.df.columns.tolist()
        for column in column_list:
            self._add_column(column=column)
            if units_list != []:
                if str(units_list[pos]) == 'nan':
                    self.cols[column]['unit'] = False
                else:
                    self.cols[column]['unit'] = units_list[pos]
            pos += 1

        # lg.info(json.dumps(self.cols, sort_keys=True, indent=4))

        if self.original_type == 'whp':
            self.df = self.df[1:-1].reset_index(drop=True)          # rewrite index column and remove the units row

    def _add_column(self, column='', units=False):
        ''' Adds a column to the self.cols dictionary
            This dictionary is useful to select some columns by type
        '''
        if column not in self.get_columns_by_type(['all']):
            self.cols[column] = {
                'types': [],
                'unit': units,
            }
            if column.endswith(FLAG_END):
                self.cols[column]['types'] += ['param_flag']
                flags_not_to_qc = [x + FLAG_END for x in NON_QC_PARAMS]
                if column not in flags_not_to_qc:
                    self.cols[column]['types'] += ['qc_param_flag']
            else:
                if column in REQUIRED_COLUMNS:
                    self.cols[column]['types'] += ['required']
                elif column not in NON_QC_PARAMS:
                    self.cols[column]['types'] += ['param']
                else:
                    self.cols[column]['types'] += ['non_qc_param']

                qc_column_exceptions = NON_QC_PARAMS + REQUIRED_COLUMNS
                flag = column + FLAG_END
                column_list = self.df.columns.tolist()
                if flag not in column_list and column not in qc_column_exceptions:
                    lg.info('>> ROWS LENGTH: {}'.format(len(self.df.index)))
                    lg.info('>> CREATING FLAG: {}'.format(flag))
                    values = ['9'] * len(self.df.index)
                    self.df[flag] = values
                    self.cols[flag] = {
                        'types': ['param_flag', 'qc_param_flag'],
                        'unit': False,
                    }

    def _init_early_calculated_params(self):
        ''' Initializates the dataframe with the basic params that all csv files should have.
            If some of them do not exist in the dataframe yet they are created with the default values
        '''
        for pname in BASIC_PARAMS:
            if pname not in self.get_columns_by_type(['all']):
                if pname.endswith(FLAG_END):
                    self.df[pname] = np.array(['9'] * self.df.index.size)
                else:
                    self.df[pname] = np.array([np.nan] * self.df.index.size)
                self._add_column(column=pname, units=False)

    def _set_attributes_from_json_file(self):
        """ The attributes (cols) are set directly from the attributes.json file """
        lg.info('-- SET ATTRIBUTES FROM JSON FILE --')
        if path.isfile(path.join(TMP, 'attributes.json')):
            with open(path.join(TMP, 'attributes.json'), 'r') as f:
                attr = json.load(f)
            self.cols = attr

    def get_columns_by_type(self, column_types=[]):
        ''' Possible types:
                * computed      - calculated parameters
                * param         - parameters
                * non_qc_param  - params without qc column
                * param_flag    - params that have qc flag columns
                * qc_param_flag - flags that were created by the application with value 2
                * required      - required columns
        '''
        if isinstance(column_types, str):
            column_types = [column_types]
        if len(column_types) == 1 and 'all' in column_types:
            column_types = [
                'computed', 'param', 'non_qc_param',
                'param_flag', 'qc_param_flag', 'required'
            ]
        res = []
        for t in column_types:
            for c in self.cols:
                if t in self.cols[c]['types']:
                    res.append(c)
        res = list(set(res))  # one column may have multiple types
        df_cols = list(self.df.columns)
        col_positions = dict(
            [(df_cols[df_cols.index(x)], df_cols.index(x)) for x in df_cols]  # {'COL1': 0, 'COL2': 1, ...}
        )
        prepaired_list = [(col_positions[x], x) for x in res]
        sorted_list = sorted(prepaired_list, key=lambda elem: elem[0])  # reordering
        final_list = [x[1] for x in sorted_list]
        return final_list

    @property
    def stations(self):
        return list(self.df.drop_duplicates(STNNBR)[STNNBR])

    def get_units(self):
        return [self.cols[x]['unit'] for x in self.cols]

    def get_plotable_columns(self):
        ''' Returns the useful columns that can be plotted,
            also discards columns that have all the values with NaN
        '''
        plot_cols = self.get_columns_by_type(['param', 'param_flag', 'qc_param_flag', 'computed'])
        final_cols = list(plot_cols)
        for c in plot_cols:
            if self.df[c].isnull().all():
                final_cols.remove(c)
        final_cols.sort()
        return final_cols

    def get_plot_cp_params(self):
        return {
            'plotable_columns': self.get_plotable_columns(),
            'computed': self.get_columns_by_type(['computed'])
        }

    def is_flag(self, flag):
        if flag[-7:] == FLAG_END and flag in self.get_columns_by_type(['param_flag', 'qc_param_flag']):
            return True
        else:
            return False

    def _set_df(self, from_scratch=False):
        """ it creates the self.df dataframe object
            taking into account if data.csv is created or not

            @from_scratch: boolean to force the loading from scratch
        """
        lg.info('-- SET DF')
        self.df = pd.read_csv(
            filepath_or_buffer=self.filepath_or_buffer,
            comment='#',
            delimiter=',',
            skip_blank_lines=True,
            engine='c',                 # engine='python' is more versatile, 'c' is faster
            dtype=str,                  # useful to make some replacements before casting to numeric values
            skiprows=self.skiprows,
            # verbose=False             # indicates the number of NA values placed in non-numeric columns
        )
        # lg.info('\n\n>> DF: \n\n{}'.format(self.df))
        self.df.replace('\s', '', regex=True, inplace=True)  # cleans spaces: \r and \n are managed by read_csv
        self.df.columns = self._sanitize(self.df.columns)    # remove spaces from columns

    def _set_moves(self):
        """ create the self.moves dataframe object
            taking into account if moves.csv is already created or not
        """
        if path.isfile(MOVES_CSV) and os.stat(MOVES_CSV).st_size != 0:
            self.moves = pd.read_csv(
                MOVES_CSV, delimiter=',', skip_blank_lines=True,
                verbose=True, engine='python', index_col=0, dtype=str
            )
        else:
            columns = [
                'date', 'action', 'stnnbr', 'castno',
                'btlnbr', 'latitude', 'longitude', 'param', 'value', 'description'
            ]
            self.moves = pd.DataFrame(columns=columns, dtype=str)

    def _set_hash_ids(self):
        """ Create a column id for the whp-exchange files
            this new column is a hash of these fields combined:
                * STNNBR     station number
                * CASTNO     cast number (it may exist or not)
                * BTLNBR     bottle number (it may exist or not)
                * LATITUDE   latitude
                * LONGITUDE  longitude
        """
        self.df['HASH_ID'] = self.df[[
            'STNNBR', 'CASTNO', 'BTLNBR', 'LATITUDE', 'LONGITUDE'   # if BTLNBR is NaN the hash is made correctly as well
        ]].astype(str).apply(                                       # astype is 4x slower than apply
            lambda x: hashlib.sha256(str.encode(str(tuple(x)))).hexdigest(), axis=1
        )
        self.df = self.df.set_index(['HASH_ID'])

    def _validate_required_columns(self):
        lg.warning('-- VALIDATE REQUIRED COLUMNS')
        lg.warning('>> ALL COLUMNS: {}'.format(self.get_columns_by_type(['all'])))
        if(not set(self.get_columns_by_type(['all'])).issuperset(REQUIRED_COLUMNS)):
            missing_columns = ', '.join(list(set(REQUIRED_COLUMNS) - set(self.get_columns_by_type(['all']))))
            raise ValidationError(
                'Missing required columns in the file: [{}]'.format(missing_columns),
                rollback='cruise_data'
            )

    def _sanitize(self, names):
        result = []
        for name in names:
            name = name.replace('PH_TS', 'PH_TOT')
            name = name.replace('NO2NO3','NO2_NO3')
            name = name.replace('-', '_')
            name = name.replace('+', '_')
            name = name.replace(' ', '')
            result.append(name)
        return result

    def _replace_missing_values(self):
        ''' Replaces the -990.0, -999.00, etc values to NaN.
            There will be strings and floats in the same column because NaN is considered a float64
            and this step should be before the numeric conversion
        '''
        lg.info('-- REPLACE MISSING VALUES (-999 >> NaN)')
        # self.df = self.df.applymap(lambda x: str.strip(x))  # trim spaces, we do  this with the raw data directly
        self.df.replace(
            to_replace=NA_REGEX_LIST,
            value='', #np.nan,
            inplace=True,
            regex=True,
        )

    def _convert_data_to_number(self):
        ''' Converts the DF from string to numeric values
            downcasting the resulting data to the smallest numerical dtype possible (int8 is the minimum)

            If the column has float values, all the column will have
            the same number of decimals (the maximum, but the zero is not taking into account)

            If a cell of a column with dtype=np.int8 is assign to some int64 value, then the column
            is completely converted to int64
        '''
        self.df = self.df.apply(lambda x: pd.to_numeric(x, errors='ignore', downcast='integer'))

        # if the new values are float >> check the original string to make the rounding well

        self.df = self.df.round(5)  # TODO: round with the original number of decimals >> float comparison

    def update_flag_values(self, column, new_flag_value, row_indices):
        """ This method is executed mainly when a flag is pressed to update the values
                * column: it is the column to update, only one column
                * new_flag_value: it is the flag value
        """
        lg.info('-- UPDATE DATA --')

        lg.info('>> COLUMN: %s | VALUE: %s | ROWS: %s' % (column, new_flag_value, row_indices))
        # lg.info('\n\nData previous changed: \n\n%s' % self.df[[ column ]].iloc[row_indices])

        hash_index_list = self.df.index[row_indices]
        self.df.loc[hash_index_list,(column)] = new_flag_value

        # lg.info('\n\nData after changed: \n\n%s' % self.df[[ column ]].iloc[row_indices])

        # Update the action log
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        action = 'QC Update'

        for row in row_indices:
            stnnbr = self.df[[ 'STNNBR' ]].iloc[row][0]
            castno = self.df[[ 'CASTNO' ]].iloc[row][0]
            btlnbr = self.df[[ 'BTLNBR' ]].iloc[row][0]
            latitude = self.df[[ 'LATITUDE' ]].iloc[row][0]
            longitude = self.df[[ 'LONGITUDE' ]].iloc[row][0]
            description = '{COLUMN} flag was updated to {FLAG}, in [station {STNNBR}, cast number {CASTNO}, bottle {BTLNBR}, latitude {LATITUDE}, longitude {LONGITUDE}]'.format(
                COLUMN=column, FLAG=new_flag_value, STNNBR=stnnbr, CASTNO=castno,
                BTLNBR=btlnbr, LATITUDE=latitude, LONGITUDE=longitude,
            )
            lg.info('>> MOVES LOG: {}, {}, {}'.format(date, action, description))

            fields = [date, action, stnnbr, castno, btlnbr, latitude, longitude, column, new_flag_value, description]
            if not self.moves.empty:
                last_pos = self.moves.tail(1).index[0]
                self.moves.loc[last_pos + 1] = fields  # fastest way to add a row at the end
            else:
                self.moves.loc[0] = fields

        self.save_tmp_data()

    def add_moves_element(self, action, description):
        lg.info('-- ADD ELEM TO MOVES.csv --')
        date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not self.moves.empty:
            last_pos = self.moves.tail(1).index[0]
            self.moves.loc[last_pos + 1] = [date, action, '', '', '', '', '', '', '', description]  # fastest way to add a row at the end
        else:
            self.moves.loc[0] = [date, action, '', '', '', '', '', '', '', description]