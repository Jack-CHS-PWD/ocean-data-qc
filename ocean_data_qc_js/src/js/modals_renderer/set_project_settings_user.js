// //////////////////////////////////////////////////////////////////////
//  License, authors, contributors and copyright information at:       //
//  AUTHORS and LICENSE files at the root folder of this application   //
// //////////////////////////////////////////////////////////////////////

"use strict";

const path = require('path');
const app_module_path = require('app-module-path');
app_module_path.addPath(path.join(__dirname, '../modules'));
app_module_path.addPath(path.join(__dirname, '../renderer_modules'));
app_module_path.addPath(__dirname);

const {ipcRenderer} = require('electron');
const fs = require('fs');                             // file system module
const rmdir = require('rimraf');

const loc = require('locations');
const lg = require('logging');
const data = require('data');
const tools = require('tools');
const server_renderer = require('server_renderer');


module.exports = {
    init: function(){
        var self = this;
        ipcRenderer.on('project-settings-user', (event, args) => {
            lg.info('-- SET PROJECT SETTINGS USER');
            var url = path.join(loc.modals, 'set_project_settings_user.html');
            tools.load_modal(url, function() {
                $('#project_name').val(path.basename(args.csv_file));
                self.init_files(args.csv_file);

                self.original_csv_pipe.on('close', function(){
                    var _checkBokehSate = setInterval(function() {
                        if ($('body').data('bokeh_state') == 'ready') {  // check if bokeh is already loaded
                            clearInterval(_checkBokehSate);
                            self.init_form();
                        }
                    }, 100);
                });
            });
        });
    },

    init_files: function(csv_file=false) {
        // TODO: Try to move all this initialization to python, as much as possible
        var self = this;

        // TMP FOLDER
        if (!fs.existsSync(loc.proj_files)) {
            fs.mkdirSync(loc.proj_files);
        }

        // ORIGINAL.CSV
        if (csv_file != false) {
            self.original_csv_pipe = fs.createReadStream(csv_file).pipe(
                fs.createWriteStream(
                    path.join(loc.proj_files, 'original.csv')
                )
            );
            self.original_csv_pipe.on('error', function() {
                lg.error('The file could not be opened!!');
                tools.showModal(
                    'ERROR',
                    'The file could not be opened!<br />It could not be copied to the temp folder'
                );
            })
        }

        // MOVES.CSV
        fs.closeSync(fs.openSync(path.join(loc.proj_files, 'moves.csv'), 'w'));

        // CUSTOM_SETTINGS.CSV  >>  PROJ_SETTINGS
        self.custom_settings_copy = fs.createReadStream(path.join(loc.custom_settings)).pipe(
            fs.createWriteStream(
                path.join(loc.proj_settings)
            )
        );
        self.custom_settings_copy.on('error', function() {
            lg.error('The file could not be opened!!');
            tools.showModal(
                'ERROR',
                'The file could not be opened!<br />' +
                'The default settings file could not be opened'
            );
        })
    },

    init_form: function() {
        var self = this;
        var call_params = {
            'object': 'cruise.data.handler',
            'method': 'get_cruise_data_columns',
        }
        tools.call_promise(call_params).then((cols_dict) => {
            self.file_columns = cols_dict['cols'];
            self.cps_columns = cols_dict['cps'];
            self.params = cols_dict['params'];
            var qc_plot_tabs = data.get('qc_plot_tabs', loc.custom_settings);
            var qc_plot_tabs_final = {};
            Object.keys(qc_plot_tabs).forEach(function(tab) {
                qc_plot_tabs[tab].forEach(function (graph) {
                    if (self.file_columns.includes(tab)) {
                        if (self.file_columns.includes(graph.x) && self.file_columns.includes(graph.y)) {
                            if (tab in qc_plot_tabs_final) {
                                qc_plot_tabs_final[tab].push(graph);
                            } else {
                                qc_plot_tabs_final[tab] = [graph];
                            }
                        }
                    }
                });
            });
            self.create_qc_tab_tables(qc_plot_tabs_final);
            self.load_buttons();
            self.load_accept_and_plot_button(); // different implementation in the bokeh modal form

            $('#discard_plotting, .close').on('click', function() {  // on unload
                if (fs.existsSync(loc.proj_files)) {
                    rmdir(loc.proj_files, function () {
                        // TODO: if an error occur, then the window is shown again, or an error appears
                        lg.info('~~ PROJECT DIRECTORY DELETED');
                    });
                }
                var call_params = {
                    'object': 'bokeh.loader',
                    'method': 'reset_env_cruise_data',
                }
                tools.call_promise(call_params).then((result) => {
                    lg.info('>> ENV CRUISE DATA RESET')
                });
            });

            tools.show_default_cursor();
            $('#modal_trigger_set_project_settings').click();
        });
    },

    load_buttons: function() {
        var self = this;
        $('#add_new_tab').on('click', function() {
            var new_fieldset = $('fieldset:first').clone();
            $('fieldset:last').after(new_fieldset);
            new_fieldset.slideDown();
            self.params.forEach(function(column) {
                new_fieldset.find('select[name=tab_title]').append($('<option>', {
                    value: column,
                    text: column,
                }));
            })
            self.file_columns.forEach(function(column) {
                if (self.cps_columns.includes(column)) {
                    lg.warn('>> ADDING COMPUTED CLASS')
                    new_fieldset.find('.qc_tabs_table_row select').append($('<option>', {
                        value: column,
                        text : column,
                        class: 'layout_computed_param_column'
                    }));
                } else {
                    new_fieldset.find('.qc_tabs_table_row select').append($('<option>', {
                        value: column,
                        text : column
                    }));
                }
            });
            new_fieldset.find('.add_new_plot').click(function() {
                var new_row = self.get_new_row();
                $(this).parent().parent().before(new_row);
                $('.delete_graph').on('click', function() {
                    $(this).parent().parent().remove();
                });
            });

            // reindex fieldsets
            var index = 0;
            var first = true;
            $('fieldset').each(function() {
                if (first == true) {
                    first = false;
                } else {
                    lg.info('>> QC TABS TABLE ID: ' + $(this).attr('id'));
                    $(this).attr('id', 'qc_tabs_table-' + index);
                    index++;
                }
            });
            self.load_row_buttons(new_fieldset);
        });

    },

    load_accept_and_plot_button() {
        $('#accept_and_plot').on('click', function() {
            // validations
            if($('#project_name').val() == '') {
                tools.show_modal({
                    'msg_type': 'html',
                    'type': 'VALIDATION ERROR',
                    'msg': '<p>The project name field must be filled.</p> <p>It is a required field.</p>',
                });
                return;
            }
            if ($('#qc_tabs_table-0').length == 0) {
                tools.show_modal({
                    'type': 'VALIDATION ERROR',
                    'msg': 'At least there should be one tab with plots filled.'
                });
                return;
            }

            // TODO: check also at least 1 element inside the tab

            data.set({
                'project_state': 'modified',                // because it is new, not saved yet
                'project_name': $('#project_name').val(),
            }, loc.proj_settings);

            var first = true;
            var qc_plot_tabs = {}
            $('fieldset').each(function() {
                if (first == true) {
                    first = false;
                } else {
                    var tab = $(this).find('select[name=tab_title]').val();
                    lg.info('>> CURRENT TAB: ' + tab);
                    qc_plot_tabs[tab] = []
                    var first_row = true;
                    $(this).find('.qc_tabs_table_row').each(function() {
                        lg.info('>> CURRENT ROW (TITLE): ' + $(this).find('input[name=title]').val());
                        if (first_row == true) {
                            first_row = false;
                        } else {
                            var title = $(this).find('input[name=title]').val();
                            var x_axis = $(this).find('select[name=x_axis]').val();
                            var y_axis = $(this).find('select[name=y_axis]').val();
                            if (title == '') {
                                title = x_axis + ' vs ' + y_axis;
                            }
                            qc_plot_tabs[tab].push({
                                'title': title,
                                'x': x_axis,
                                'y': y_axis
                            });
                        }
                    })
                }
            });
            data.set({'qc_plot_tabs': qc_plot_tabs }, loc.proj_settings);
            lg.info('>> PROJECT SETTINGS: ' + JSON.stringify(loc.proj_settings, null, 4));
            $('#dummy_close').click();
            server_renderer.go_to_bokeh();
        });
    },

    create_qc_tab_tables: function(qc_plot_tabs={}) {
        lg.info('-- CREATE QC TAB TABLES');
        var self = this;
        // lg.info('>> TABS: ' + JSON.stringify(qc_plot_tabs, null, 4));

        if (qc_plot_tabs == {} || self.file_columns == []) {
            lg.error('>> QC PLOT TABS EMPTY or THE FILE DOES NOT HAVE ANY COLUMNS');
            return;
        }

        var index = 0;
        Object.keys(qc_plot_tabs).forEach(function(tab) {
            // TODO: check here if the tab is going to have graphs

            var new_qc_tab_div = $("#qc_tabs_table").clone();
            new_qc_tab_div.attr('id', 'qc_tabs_table-' + index);
            new_qc_tab_div.find('.add_new_plot').click(function() {
                var new_row = self.get_new_row();
                $(this).parent().parent().before(new_row);
                $('.delete_graph').on('click', function() {
                    $(this).parent().parent().remove();
                });
            });
            self.params.forEach(function (column) {
                new_qc_tab_div.find('select[name=tab_title]').append($('<option>', {
                    value: column,
                    text: column,
                }));
            });
            new_qc_tab_div.find('select[name=tab_title]').val(tab);

            qc_plot_tabs[tab].forEach(function (graph) {
                var new_row = self.get_new_row(graph);
                new_qc_tab_div.find('tbody tr:last-child').before(new_row);
            });

            new_qc_tab_div.appendTo("#qc_tabs_container").css('display', 'block');
            index++;
            self.load_row_buttons(new_qc_tab_div)
        });
    },

    load_row_buttons: function(fieldset) {
        fieldset.find('.delete_tab').on('click', function() {
            if ($('#qc_tabs_table-1').length != 0) {
                $(this).parent().parent().slideUp('fast', function() {
                    $(this).remove();
                    // reindex fieldsets
                    var index = 0;
                    var first = true;
                    $('fieldset').each(function() {
                        if (first == true) {
                            first = false;
                        } else {
                            $(this).attr('id', 'qc_tabs_table-' + index);
                            index++;
                        }
                    });
                });
            } else {
                tools.showModal(
                    'ERROR',
                    'You should show at least one tab on the project layout.'
                );
            }
        });

        $('.delete_graph').on('click', function() {
            $(this).parent().parent().remove();
        });
    },

    get_new_row: function(graph=null) {
        var self = this;
        var new_row = $('#qc_tabs_table .qc_tabs_table_row:first').clone();
        self.file_columns.forEach(function (column) {
            var option_attrs = {
                value: column,
                text : column,
            };
            if (self.cps_columns.includes(column)) {
                option_attrs['class'] = 'layout_computed_param_column';  // green color
            }
            new_row.find('select[name=x_axis]').append($('<option>', option_attrs));
            new_row.find('select[name=y_axis]').append($('<option>', option_attrs));
        });
        if (graph != null) {
            new_row.find('input[name=title]').val(graph.title);
            new_row.find('select[name=x_axis]').val(graph.x);
            new_row.find('select[name=y_axis]').val(graph.y);
        }
        new_row.css('display', 'table-row');
        // lg.info('>> NEW ROW: ' + new_row.get());
        return new_row;
    },
}