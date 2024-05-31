$(function () {
    function UlendoCaasViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.last_axis_click = 'unknown';

        self.clearAllButtonStates = function () {
            // Reset the state of accelerometer button
            acclrmtr_connect_btn.className = "acclrmtr_connect_btn btn";
            var calibration_state_labels = document.getElementById('calibration_state_labels');
            var calibrate_x_status_label = document.getElementById('calibrate_x_status_label');
            var calibrate_y_status_label = document.getElementById('calibrate_y_status_label');
            var calibration_instructions = document.getElementById('calibration_instructions');
            calibration_state_labels.style.visibility = "hidden";
            calibrate_x_status_label.style.visibility = "hidden";
            calibrate_y_status_label.style.visibility = "hidden";
            calibration_instructions.style.display = "none";

            // Reset the state of Calibrate button
            var calibrate_axis_btns = document.querySelectorAll(".calibrate_axis_btn_group button");
            for (var i = 0; i < calibrate_axis_btns.length; i++) {
                calibrate_axis_btns[i].className = "calibrate_axis_btn btn";
            }

            // Reset the state of shaper selection buttons.
            var select_calibration_btns = document.querySelectorAll(".calibrate_select_btn_group_content  button");
            for (var i = 0; i < select_calibration_btns.length; i++) {
                select_calibration_btns[i].className = "select_calibration_btn_NOTSELECTED_style btn";
            }

            load_calibration_btn.className = "load_calibration_btn btn btn-primary";

            save_calibration_btn.className = "save_calibration_btn btn btn-primary";

            clear_session_btn.className = "clear_session_btn btn";
        }

        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin != "ulendocaas") { return; }


            if (data.type == "acclrmtr_live_data") {
                let series1 = { x: data.values_x, y: data.values_y, mode: "lines", name: 'Axis Acceleration' };
                var layout = {
                    width: $('#calibration_results_graph').parent().width(),
                    title: 'Accelerometer Data',
                    xaxis: { title: 'Time [sec]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Acceleration [mm/sec/sec]', showline: false },
                    font: {
                        family: "Helvetica",
                        size: 11.6667
                    }
                };
                var config = { responsive: true }
                Plotly.newPlot('acclrmtr_live_data_graph', [series1], layout, config);
                return;
            }


            if (data.type == "calibration_result") {
                let series1 = { x: data.w_bp, y: data.G, mode: "lines", name: 'Before<br>Shaper' };
                let series2 = { x: data.w_bp, y: data.compensator_mag, mode: "lines", name: 'Shaper<br>Response' };
                let series3 = { x: data.w_bp, y: data.new_mag, mode: "lines", name: 'After<br>Shaper' };
                var layout = {
                    width: $('#calibration_results_graph').parent().width(),
                    title: ''.concat(data.axis.toUpperCase(), ' Axis Calibration Preview using ', data.istype.toUpperCase()),
                    xaxis: { title: 'Frequency [Hz]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Magnitude', showline: false },
                    font: {
                        family: "Helvetica",
                        size: 11.6667
                    }
                };
                var config = { responsive: true }
                Plotly.newPlot('calibration_results_graph', [series1, series2, series3], layout, config);
            }

            if (data.type == "verification_result") {
                let series1 = { x: data.w_bp, y: data.oldG, mode: "lines", name: 'Uncmpnstd Rspns' };
                let series2 = { x: data.w_bp, y: data.compensator_mag, mode: "lines", name: 'Cmpnstr Rspns' };
                let series3 = { x: data.w_bp, y: data.new_mag, mode: "lines", name: 'New Rspns Estim' };
                let series4 = { x: data.w_bp, y: data.G, mode: "lines", name: 'New Rspns Meas' };
                var layout = {
                    title: 'Verification Result',
                    xaxis: { title: 'Frequency [Hz]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Magnitude', showline: false }
                };
                Plotly.newPlot('verification_results_graph', [series1, series2, series3, series4], layout);
            }


            if (data.type == "clear_calibration_result") {
                if (typeof calibration_results_graph.data != "undefined") {
                    while (calibration_results_graph.data.length > 0) { Plotly.deleteTraces('calibration_results_graph', [0]); }
                }
            }


            if (data.type == "clear_verification_result") {
                if (typeof verification_results_graph.data != "undefined") {
                    while (verification_results_graph.data.length > 0) { Plotly.deleteTraces('verification_results_graph', [0]); }
                }
            }

            if (data.type == "logger_info") {
                output_log.innerHTML += data.message + '<br>';
            }

            if (data.type == "layout_status_1") {
                self.clearAllButtonStates();
                acclrmtr_connect_btn.disabled = data.acclrmtr_connect_btn_disabled;
                var calibration_state_labels = document.getElementById('calibration_state_labels');
                var calibrate_x_status_label = document.getElementById('calibrate_x_status_label');
                var calibrate_y_status_label = document.getElementById('calibrate_y_status_label');
                var calibration_instructions = document.getElementById('calibration_instructions');
                var license_status = document.getElementById('license_status');
                var license_status_message = document.getElementById('license_status_message');

                acclrmtr_connect_btn.classList.add("".concat(data.acclrmtr_connect_btn_state, "_style"));
                calibrate_x_axis_btn.classList.add("".concat(data.calibrate_x_axis_btn_state, "_style"));
                calibrate_y_axis_btn.classList.add("".concat(data.calibrate_y_axis_btn_state, "_style"));

                console.log('is_active_client', data.is_active_client)
                if (data.is_active_client) {
                    self.removeClass(license_status, "alert-");
                    license_status.classList.add("alert-success");
                    license_status.classList.add("alert-block");
                    license_status_message.innerText = "Good";
                } else {
                    self.removeClass(license_status, "alert-");
                    license_status.classList.add("alert-warning");
                    license_status.classList.add("alert-block");
                    license_status_message.innerText = "Not Activated";
                }

                if (data.acclrmtr_connect_btn_state == 'NOTCONNECTED') {
                    acclrmtr_connect_btn.innerHTML = '<i class="icon-off"></i> Connect';
                }
                else if (data.acclrmtr_connect_btn_state == 'CONNECTING') {
                    acclrmtr_connect_btn.innerHTML = '<i class="icon-off"></i> Connecting';
                }

                if (data.acclrmtr_connect_btn_state == 'CONNECTED') {
                    acclrmtr_connect_btn.innerHTML = '<i class="icon-off"></i> Connected';
                    acclrmtr_connect_btn.classList.add("btn-success");
                    calibrate_x_axis_btn.style.display = "inline";   // TODO: control the visibility of buttons server-side
                    // in order to match the rest of the software flow.
                    calibrate_y_axis_btn.style.display = "inline";
                    calibration_state_labels.style.visibility = "visible";
                } else {
                    calibrate_x_axis_btn.style.display = "none";
                    calibrate_y_axis_btn.style.display = "none";
                }

                calibrate_select_btn_group_id.style.display = "none";
                calibrate_select_btn_group_id.style.display = "none";
                save_calibration_btn.style.display = "none";
                if (data._state == 'NOTCALIBRATED') { calibrate_x_axis_btn.innerText = 'Calibrate X'; }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATING') {
                    let message = "Calibrating";
                    calibrate_x_axis_btn.innerText = 'Calibrate X';
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_x_status_label.classList.add("label-warning");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit";
                    calibrate_y_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible
                }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONREADY') {
                    let message = "Ready";
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_select_btn_group_id.style.display = "inline-block";
                    calibrate_x_status_label.classList.add("label-info");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit";
                    calibrate_y_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible
                    calibration_instructions.style.display = "block";
                }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONAPPLIED') {
                    let message = "Calibrated";
                    save_calibration_btn.style.display = "block";
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_x_status_label.classList.add("label-success");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit"; //inherits parent style
                    calibrate_y_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible
                    calibration_instructions.style.display = "block";
                    // after loading without re-running the calibration routing.
                }

                if (data.calibrate_y_axis_btn_state == 'NOTCALIBRATED') { calibrate_y_axis_btn.innerText = 'Calibrate Y'; }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATING') {
                    let message = "Calibrating";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_y_status_label.classList.add("label-warning");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                    calibrate_x_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible
                }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONREADY') {
                    let message = "Ready";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_select_btn_group_id.style.display = "inline-block";
                    calibrate_y_status_label.classList.add("label-info");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                    calibrate_x_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible// this to maintain spacing for flex, it would still be invisible
                    calibration_instructions.style.display = "block";
                }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONAPPLIED') {
                    let message = "Calibrated";
                    save_calibration_btn.style.display = "block";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_y_status_label.classList.add("label-success");
                    calibrate_x_status_label.innerText = message;
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                    calibrate_x_status_label.style.visibility = "hidden"; // this to maintain spacing for flex, it would still be invisible
                    calibration_instructions.style.display = "block";
                    // after loading without re-running the calibration routing.
                }

                if (data.select_zv_btn_state == 'SELECTED') {
                    select_zv_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_zv_cal_btn.classList.remove('SELECTED_style');
                }
                if (data.select_zvd_btn_state == 'SELECTED') {
                    select_zvd_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_zvd_cal_btn.classList.remove('SELECTED_style');
                }
                if (data.select_mzv_btn_state == 'SELECTED') {
                    select_mzv_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_mzv_cal_btn.classList.remove('SELECTED_style');
                }
                if (data.select_ei_btn_state == 'SELECTED') {
                    select_ei_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_ei_cal_btn.classList.remove('SELECTED_style');
                }
                if (data.select_ei2h_btn_state == 'SELECTED') {
                    select_ei2h_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_ei2h_cal_btn.classList.remove('SELECTED_style');
                }
                if (data.select_ei3h_btn_state == 'SELECTED') {
                    select_ei3h_cal_btn.classList.add('SELECTED_style');
                } else {
                    select_ei3h_cal_btn.classList.remove('SELECTED_style');
                }

                save_calibration_btn.classList.add("".concat(data.save_calibration_btn_state, "_style"));

                if (data.select_zv_btn_state == "SELECTED" ||
                    data.select_zvd_btn_state == "SELECTED" ||
                    data.select_mzv_btn_state == "SELECTED" ||
                    data.select_ei_btn_state == "SELECTED" ||
                    data.select_ei2h_btn_state == "SELECTED" ||
                    data.select_ei3h_btn_state == "SELECTED") {
                    load_calibration_btn.style.display = "block";
                } else {
                    load_calibration_btn.style.display = "none";
                }

                if (data.load_calibration_btn_state == 'NOTLOADED') { load_calibration_btn.innerText = 'Load and Verify Calibration'; }
                if (data.load_calibration_btn_state == 'LOADING') {
                    load_calibration_btn.innerText = 'Verifying Calibration';
                    self.removeClass(load_calibration_btn, "btn-"); // remove old button color
                    load_calibration_btn.classList.add("btn-warning");
                }
                if (data.load_calibration_btn_state == 'LOADED') {
                    load_calibration_btn.innerText = 'Calibration Loaded and Verified';
                    self.removeClass(load_calibration_btn, "btn-"); // remove old button color
                    load_calibration_btn.classList.add("btn-success");
                }

                load_calibration_btn.classList.add("".concat(data.load_calibration_btn_state, "_style"));
                calibrate_x_axis_btn.disabled = data.calibrate_x_axis_btn_disabled;
                calibrate_y_axis_btn.disabled = data.calibrate_y_axis_btn_disabled;
                select_zv_cal_btn.disabled = data.select_zv_btn_disabled;
                select_zvd_cal_btn.disabled = data.select_zvd_btn_disabled;
                select_mzv_cal_btn.disabled = data.select_mzv_btn_disabled;
                select_ei_cal_btn.disabled = data.select_ei_btn_disabled;
                select_ei2h_cal_btn.disabled = data.select_ei2h_btn_disabled;
                select_ei3h_cal_btn.disabled = data.select_ei3h_btn_disabled;
                load_calibration_btn.disabled = data.load_calibration_btn_disabled;
                save_calibration_btn.disabled = data.save_calibration_btn_disabled;

                clear_session_btn.disabled = data.clear_session_btn_disabled;

                if (data.vtol_slider_visible) {
                    const curVibrationTolerance = document.getElementById("vtolslider").value;
                    document.getElementById("vtol_group").style.display = 'flex';
                    document.getElementById("vibration_tol_val").innerText = curVibrationTolerance; // set default Vibration Tolerance value
                }
                else document.getElementById("vtol_group").style.display = 'none';

                return;
            }

            if (data.type == "popup") {
                new PNotify({
                    title: data.title,
                    text: data.message,
                    type: data.popup,
                    hide: data.hide
                });
                return;
            }

            if (data.type == "prompt_popup") {
                if (typeof server_prompt !== 'undefined') {
                    server_prompt.remove();
                    server_prompt = undefined;
                }
                server_prompt = new PNotify({
                    title: gettext(data.title),
                    text: gettext(data.message),
                    hide: false,
                    confirm: {
                        confirm: true,
                        buttons: [
                            {
                                text: gettext("Cancel"),
                                click: function () {
                                    OctoPrint.simpleApiCommand("ulendocaas", "prompt_cancel_click");
                                    server_prompt.remove();
                                    server_prompt = undefined;
                                }
                            },
                            {
                                text: gettext("Proceed"),
                                addClass: "btn-primary",
                                click: function () {
                                    OctoPrint.simpleApiCommand("ulendocaas", "prompt_proceed_click");
                                    server_prompt.remove();
                                    server_prompt = undefined;
                                }
                            }
                        ]
                    },
                    buttons: {
                        closer: false,
                        sticker: false
                    }
                });
                return;
            }

            if (data.type == "printer_connection_status") {
                if (data.status == 'connected') {
                    motion_prompt = new PNotify({
                        title: gettext("Axis Motion Imminent"),
                        text: gettext(
                            "<p>The axis will begin moving for calibration. Verify motion is clear and proceed.</p>"
                        ),
                        hide: false,
                        confirm: {
                            confirm: true,
                            buttons: [
                                {
                                    text: gettext("Cancel"),
                                    click: function () {
                                        motion_prompt.remove();
                                        motion_prompt = undefined;
                                    }
                                },
                                {
                                    text: gettext("Proceed"),
                                    addClass: "btn-primary",
                                    click: function () {
                                        if (self.last_axis_click == 'load') {
                                            Plotly.purge('verification_results_graph');
                                            OctoPrint.simpleApiCommand("ulendocaas", "load_calibration_btn_click");
                                        }
                                        else {
                                            Plotly.purge('calibration_results_graph');
                                            Plotly.purge('verification_results_graph');
                                            OctoPrint.simpleApiCommand("ulendocaas", "calibrate_axis_btn_click", { axis: self.last_axis_click });
                                        }
                                        motion_prompt.remove();
                                        motion_prompt = undefined;
                                    }
                                }
                            ]
                        },
                        buttons: {
                            closer: false,
                            sticker: false
                        }
                    });
                    return;
                } else {
                    new PNotify({
                        title: 'Printer not connected.',
                        text: 'Printer must be connected in order to start calibration.',
                        type: 'error',
                        hide: true
                    });
                    return;
                }
            }

        };

        self.removeClass = function (element, prefix) {
            var classes = element.className.split(" ").filter(function (c) {
                return c.lastIndexOf(prefix, 0) !== 0;
            });
            element.className = classes.join(" ").trim();
        }

        self.onClickAcclrmtrConnectBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "acclrmtr_connect_btn_click");
        };

        self.onClickCalibrateXAxisBtn = function () {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'x';
            OctoPrint.simpleApiCommand("ulendocaas", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickCalibrateYAxisBtn = function () {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'y';
            OctoPrint.simpleApiCommand("ulendocaas", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickLoadCalibrationBtn = function () {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'load';
            OctoPrint.simpleApiCommand("ulendocaas", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickSelectZvCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "zv" });
        }
        self.onClickSelectZvdCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "zvd" });
        }
        self.onClickSelectMzvCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "mzv" });
        }
        self.onClickSelectEiCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "ei" });
        }
        self.onClickSelectEi2hCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "ei2h" });
        }
        self.onClickSelectEi3hCalBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "select_calibration_btn_click", { type: "ei3h" });
        }

        document.getElementById("vtolslider").oninput = function () {
            document.getElementById("vibration_tol_val").innerText = vtolslider.value;
            OctoPrint.simpleApiCommand("ulendocaas", "vtol_slider_update", { val: vtolslider.value });
        };

        self.onClickSaveCalibrationBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "save_calibration_btn_click");
        }

        self.onClickClearSessionBtn = function () {
            if (typeof clear_session_prompt !== 'undefined') {
                clear_session_prompt.remove();
                clear_session_prompt = undefined;
            }
            clear_session_prompt = new PNotify({
                title: gettext("Confirm Clear Session"),
                text: gettext(
                    "<p>Are you sure you want to clear the current session?</p>"
                ),
                hide: false,
                confirm: {
                    confirm: true,
                    buttons: [
                        {
                            text: gettext("Cancel"),
                            click: function () {
                                clear_session_prompt.remove();
                                clear_session_prompt = undefined;
                            }
                        },
                        {
                            text: gettext("Yes"),
                            addClass: "btn-primary",
                            click: function () {
                                OctoPrint.simpleApiCommand("ulendocaas", "clear_session_btn_click");

                                // Delete all the graphs created.
                                Plotly.purge('acclrmtr_live_data_graph');
                                Plotly.purge('calibration_results_graph');
                                Plotly.purge('verification_results_graph');
                                // Scroll to top of the document.
                                document.body.scrollTop = 0;
                                document.documentElement.scrollTop = 0;

                                output_log.innerHTML = '';

                                clear_session_prompt.remove();
                                clear_session_prompt = undefined;
                            }
                        }
                    ]
                },
                buttons: {
                    closer: false,
                    sticker: false
                }
            });
            return;
        }
        // ko.observable is used to create reactive data models. 
        // When you change the value of an observable, any part of your application that depends on 
        // that value will automatically update to reflect the new value. 
        self.license_status = ko.observable(false);
        self.license_verifying = ko.observable(false);

        self.verifyCreds = function () {
            self.license_verifying(true)
            let license_status_wizard = document.getElementById('license_status_wizard');
            let license_status_message_wizard = document.getElementById('license_status_message_wizard');
            let body = {
                ORG: document.getElementById('org_input').value,
                ACCESSID: document.getElementById('accessId_input').value,
                MACHINEID: document.getElementById('machineId_input').value,
            }
            console.log(body)
            self.removeClass(license_status, "alert-");
            license_status_wizard.classList.add("alert-info");
            license_status_wizard.classList.add("alert-block");
            license_status_wizard.style.display = 'block';
            license_status_message_wizard.innerText = 'INFO: Verifying Credentials...';

            OctoPrint.simpleApiCommand("ulendocaas", "on_before_wizard_finish_verify_credentials", body)
                .done(function (response) {
                    // assgin the observable value
                    console.log(response);
                    self.license_status(response['license_status']);
                    if (!self.license_status()) {
                        self.removeClass(license_status_wizard, "alert-");
                        license_status_wizard.classList.add("alert-danger");
                        license_status_wizard.classList.add("alert-block");
                        license_status_message_wizard.innerText = 'ERROR: Invalid Credentials (Check your ORG, ACCESSID and MACHINEID)';
                    } else {
                        self.removeClass(license_status_wizard, "alert-");
                        license_status_wizard.classList.add("alert-success");
                        license_status_wizard.classList.add("alert-block");
                        license_status_message_wizard.innerText = 'SUCCESS: Credentials Verified!';
                    }
                    self.license_verifying(false)
                })
                .fail(function (error) {
                    console.error('Error:', error);
                });
        }

        self.onBeforeWizardFinish = function () {
            return self.license_status() && !self.license_verifying();
        }

        self.onSettingsHidden = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "on_settings_close_verify_credentials")
        }
        // This will get called before the HelloWorldViewModel gets bound to the DOM, but after its
        // dependencies have already been initialized. It is especially guaranteed that this method
        // gets called _after_ the settings have been retrieved from the OctoPrint backend and thus
        // the SettingsViewModel been properly populated.
        // self.onBeforeBinding = function() {

        // };

        // This will get called before the HelloWorldViewModel gets bound to the DOM, but after its
        // dependencies have already been initialized. It is especially guaranteed that this method
        // gets called _after_ the settings have been retrieved from the OctoPrint backend and thus
        // the SettingsViewModel been properly populated.
        self.onBeforeBinding = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "get_layout_status");
            // self.newUrl(self.settings.settings.plugins.ulendocaas.url());
            // self.newACCESS(self.settings.settings.plugins.ulendocaas.ACCESSID());
            // self.newORG(self.settings.settings.plugins.ulendocaas.ORG());
        }

        self.onAfterBinding = function() {
            self.verifyCreds();
        }
    };

    // This is how our plugin registers itself with the application, by adding some configuration
    // information to the global variable OCTOPRINT_VIEWMODELS
    OCTOPRINT_VIEWMODELS.push({
        // This is the constructor to call for instantiating the plugin
        construct: UlendoCaasViewModel,

        // This is a list of dependencies to inject into the plugin, the order which you request
        // here is the order in which the dependencies will be injected into your view model upon
        // instantiation via the parameters argument
        dependencies: ["settingsViewModel"],

        // Finally, this is the list of selectors for all elements we want this view model to be bound to.
        elements: ["#tab_plugin_ulendocaas", "#wizard_plugin_ulendocaas"]
    });
});
