// TODO: invoke an update when / if the server is reconnected

$(function() {
    function AutocalViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];

        self.last_axis_click = 'unknown';

        self.clearAllButtonStates = function() {
            // Reset the state of accelerometer button
            if (acclrmtr_connect_btn.classList.contains("acclrmtr_connect_btn_NOTCONNECTED_style")){ acclrmtr_connect_btn.classList.remove("acclrmtr_connect_btn_NOTCONNECTED_style"); }
            if (acclrmtr_connect_btn.classList.contains("acclrmtr_connect_btn_CONNECTING_style")){ acclrmtr_connect_btn.classList.remove("acclrmtr_connect_btn_CONNECTING_style"); }
            if (acclrmtr_connect_btn.classList.contains("acclrmtr_connect_btn_CONNECTED_style")){ acclrmtr_connect_btn.classList.remove("acclrmtr_connect_btn_CONNECTED_style"); }
            acclrmtr_connect_btn.classList.add("acclrmtr_connect_btn_NOTCONNECTED_style"); // default state is not connected state

            // Reset the state of Calibrate button
            var calibrate_axis_btns = document.querySelectorAll("div.calibrate_axis_btn_group button");
            for (var i = 0; i < calibrate_axis_btns.length; i++) {
                if (calibrate_axis_btns[i].classList.contains("calibrate_axis_btn_NOTCALIBRATED_style")) { calibrate_axis_btns[i].classList.remove("calibrate_axis_btn_NOTCALIBRATED_style"); }
                if (calibrate_axis_btns[i].classList.contains("calibrate_axis_btn_CALIBRATING_style")) { calibrate_axis_btns[i].classList.remove("calibrate_axis_btn_CALIBRATING_style"); }
                if (calibrate_axis_btns[i].classList.contains("calibrate_axis_btn_CALIBRATIONREADY_style")) { calibrate_axis_btns[i].classList.remove("calibrate_axis_btn_CALIBRATIONREADY_style"); }
                if (calibrate_axis_btns[i].classList.contains("calibrate_axis_btn_CALIBRATIONAPPLIED_style")) { calibrate_axis_btns[i].classList.remove("calibrate_axis_btn_CALIBRATIONAPPLIED_style"); }
                calibrate_axis_btns[i].classList.add("calibrate_axis_btn_NOTCALIBRATED_style"); // default state is not calibrated state
            }

	    // Reset the state of ZV Shapers button
            var select_calibration_btns = document.querySelectorAll("div.select_calibration_btn_group button");
            for (var i = 0; i < select_calibration_btns.length; i++) {
                if (select_calibration_btns[i].classList.contains("select_calibration_btn_NOTSELECTED_style")) { select_calibration_btns[i].classList.remove("select_calibration_btn_NOTSELECTED_style"); }
                if (select_calibration_btns[i].classList.contains("select_calibration_btn_SELECTED_style")) { select_calibration_btns[i].classList.remove("select_calibration_btn_SELECTED_style"); }
                select_calibration_btns[i].classList.add("select_calibration_btn_NOTSELECTED_style"); // default state is not selected state
            }

            // Reset the state of Load Calibration
            if (load_calibration_btn.classList.contains("load_calibration_btn_NOTLOADED_style")){ load_calibration_btn.classList.remove("load_calibration_btn_NOTLOADED_style"); }
            if (load_calibration_btn.classList.contains("load_calibration_btn_LOADING_style")){ load_calibration_btn.classList.remove("load_calibration_btn_LOADING_style"); }
            if (load_calibration_btn.classList.contains("load_calibration_btn_LOADED_style")){ load_calibration_btn.classList.remove("load_calibration_btn_LOADED_style"); }
            load_calibration_btn.classList.add("load_calibration_btn_NOTLOADED_style"); // default state is not connected state

            // Reset the state of Save Calibration
            if (save_calibration_btn.classList.contains("save_calibration_btn_NOTSAVED_style")){ save_calibration_btn.classList.remove("save_calibration_btn_NOTSAVED_style"); }
            if (save_calibration_btn.classList.contains("save_calibration_btn_SAVED_style")){ save_calibration_btn.classList.remove("save_calibration_btn_SAVED_style"); }
            save_calibration_btn.classList.add("save_calibration_btn_NOTSAVED_style"); // default state is not saved state

            // Reset the drop down button
            if (document.getElementById("select_calibration_div").classList.contains("show")){document.getElementById("select_calibration_div").classList.remove("show");}
            document.getElementById("select_calibration_div").classList.add("zv_shapers_dropDown_btn_style");
       }

        self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "autocal") { return; }


            if (data.type == "acclrmtr_live_data") {
                let series1 = { x: data.values_x, y: data.values_y, mode: "lines", name: 'Axis Acceleration' };
                var layout = { title: 'Accelerometer Data',
                    xaxis: { title: 'Time [sec]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Acceleration [mm/sec/sec]', showline: false }
                };
                Plotly.newPlot('acclrmtr_live_data_graph', [series1], layout);
                return;
            }


            if (data.type == "calibration_result") {
                let series1 = { x: data.w_bp, y: data.G, mode: "lines", name: 'Rspns' };
                let series2 = { x: data.w_bp, y: data.compensator_mag, mode: "lines", name: 'Cmpnstr Rspns' };
                let series3 = { x: data.w_bp, y: data.new_mag, mode: "lines", name: 'New Rspns Estim' };
                var layout = { title: 'Calibration Preview',
                    xaxis: { title: 'Frequency [rad/sec]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Magnitude', showline: false }
                    };
                Plotly.newPlot('calibration_results_graph', [series1, series2, series3], layout);
            }

            if (data.type == "verification_result") {
                let series1 = { x: data.w_bp, y: data.oldG, mode: "lines", name: 'Uncmpnstd Rspns' };
                let series2 = { x: data.w_bp, y: data.compensator_mag, mode: "lines", name: 'Cmpnstr Rspns' };
                let series3 = { x: data.w_bp, y: data.new_mag, mode: "lines", name: 'New Rspns Estim' };
                let series4 = { x: data.w_bp, y: data.G, mode: "lines", name: 'New Rspns Meas' };
                var layout = { title: 'Verification Result',
                    xaxis: { title: 'Frequency [rad/sec]', showgrid: false, zeroline: false, autorange: true },
                    yaxis: { title: 'Magnitude', showline: false }
                    };
                Plotly.newPlot('verification_results_graph', [series1, series2, series3, series4], layout);
            }


            if (data.type == "clear_calibration_result") {
                if (typeof calibration_results_graph.data != "undefined") {
                    while(calibration_results_graph.data.length>0) { Plotly.deleteTraces('calibration_results_graph', [0]); }
                }
            }


            if (data.type == "clear_verification_result") {
                if (typeof verification_results_graph.data != "undefined") {
                    while(verification_results_graph.data.length>0) { Plotly.deleteTraces('verification_results_graph', [0]); }
                }
            }


            if (data.type == "layout_status_1") {
                self.clearAllButtonStates();
                acclrmtr_connect_btn.disabled = data.acclrmtr_connect_btn_disabled;
                
                acclrmtr_connect_btn.classList.add("acclrmtr_connect_btn_".concat(data.acclrmtr_connect_btn_state, "_style"));
                calibrate_x_axis_btn.classList.add("calibrate_axis_btn_".concat(data.calibrate_x_axis_btn_state, "_style"));
                calibrate_y_axis_btn.classList.add("calibrate_axis_btn_".concat(data.calibrate_y_axis_btn_state, "_style"));
                
                if (data.acclrmtr_connect_btn_state == 'NOTCONNECTED') { acclrmtr_connect_btn.innerText = 'Connect Accelerometer'; }
                else if (data.acclrmtr_connect_btn_state == 'CONNECTING') { acclrmtr_connect_btn.innerText = 'Connecting'; }
                else if (data.acclrmtr_connect_btn_state == 'CONNECTED') {
                   acclrmtr_connect_btn.innerText = 'Accelerometer Connected';
                   // if pre tag already contains the connection status, ignore.
                   if(!document.getElementById('status').textContent.includes('Accelerometer Connected')){
                       document.getElementById('status').innerHTML += '<br>' + 'Accelerometer Connected';
                   }
                }

                if (data.calibrate_x_axis_btn_state == 'NOTCALIBRATED') { calibrate_x_axis_btn.innerText = 'Calibrate X'; }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATING') { calibrate_x_axis_btn.innerText = 'Calibrating X'; }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONREADY') {
                    calibrate_x_axis_btn.innerText = 'X Calibration Ready';
                   // if pre tag already contains the calibration status, ignore.
                   if(!document.getElementById('status').textContent.includes('X Calibration Ready')){
                       document.getElementById('status').innerHTML += '<br>' + 'X Calibration Ready';
                   }

                }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONAPPLIED') {
                   calibrate_x_axis_btn.innerText = 'X Calibration Applied';
                   // if pre tag already contains the calibration status, ignore.
                   if(!document.getElementById('status').textContent.includes('X Calibration Applied')){
                       document.getElementById('status').innerHTML += '<br>' + 'X Calibration Applied';
                   }

                }

                if (data.calibrate_y_axis_btn_state == 'NOTCALIBRATED') { calibrate_y_axis_btn.innerText = 'Calibrate Y'; }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATING') { calibrate_y_axis_btn.innerText = 'Calibrating Y'; }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONREADY') {
                   calibrate_y_axis_btn.innerText = 'Y Calibration Ready';
                   // if pre tag already contains the calibration status, ignore.
                   if(!document.getElementById('status').textContent.includes('Y Calibration Ready')){
                       document.getElementById('status').innerHTML += '<br>' + 'Y Calibration Ready';
                   }
                }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONAPPLIED') {
                    calibrate_y_axis_btn.innerText = 'Y Calibration Applied';
                   // if pre tag already contains the calibration status, ignore.
                   if(!document.getElementById('status').textContent.includes('Y Calibration Applied')){
                       document.getElementById('status').innerHTML += '<br>' + 'Y Calibration Applied';
                   }
                }

                if (data.load_calibration_btn_state == 'NOTLOADED') { load_calibration_btn.innerText = 'Load Calibration'; }
                if (data.load_calibration_btn_state == 'LOADING') {
                    load_calibration_btn.innerText = 'Loading Calibration';
                }
                if (data.load_calibration_btn_state == 'LOADED') {
                  load_calibration_btn.innerText = 'Calibration Loaded';
                   // if pre tag already contains the load status, ignore.
                   if(!document.getElementById('status').textContent.includes('Calibration Loaded')){
                       document.getElementById('status').innerHTML += '<br>' + 'Calibration Loaded';
                   }

                }


                zv_shapers_dropDown_btn.classList.add("zv_shapers_dropDown_btn_style");;
                document.getElementById("select_calibration_div").classList.add("select_calibration_btn_group");

                select_zv_cal_btn.classList.add("select_calibration_btn_".concat(data.select_zv_btn_state, "_style"));
                select_zvd_cal_btn.classList.add("select_calibration_btn_".concat(data.select_zvd_btn_state, "_style"));
                select_mzv_cal_btn.classList.add("select_calibration_btn_".concat(data.select_mzv_btn_state, "_style"));
                select_ei_cal_btn.classList.add("select_calibration_btn_".concat(data.select_ei_btn_state, "_style"));
                select_ei2h_cal_btn.classList.add("select_calibration_btn_".concat(data.select_ei2h_btn_state, "_style"));
                select_ei3h_cal_btn.classList.add("select_calibration_btn_".concat(data.select_ei3h_btn_state, "_style"));

                load_calibration_btn.classList.add("load_calibration_btn_".concat(data.load_calibration_btn_state, "_style"));
                
                save_calibration_btn.classList.add("save_calibration_btn_".concat(data.save_calibration_btn_state, "_style"));
                start_over_btn.classList.add("start_over_btn_style");

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

                if (data.vtol_slider_visible) { document.getElementById("vtol_group").style.display = 'flex'; }
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
                                        if (self.last_axis_click == 'load') { OctoPrint.simpleApiCommand("autocal", "load_calibration_btn_click"); }
                                        else { OctoPrint.simpleApiCommand("autocal", "calibrate_axis_btn_click", {axis: self.last_axis_click}); }
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

        self.onClickAcclrmtrConnectBtn = function() {
            document.getElementById('status').innerHTML = "Connecting Accelerometer";
            OctoPrint.simpleApiCommand("autocal", "acclrmtr_connect_btn_click");
        };

        self.onClickCalibrateXAxisBtn = function() {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'x';
            document.getElementById('status').innerHTML += "<br>" + "Calibrating X";
            OctoPrint.simpleApiCommand("autocal", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickCalibrateYAxisBtn = function() {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'y';
            document.getElementById('status').innerHTML += "<br>" + "Calibrating Y";
            OctoPrint.simpleApiCommand("autocal", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickLoadCalibrationBtn = function() {
            if (typeof motion_prompt !== 'undefined') {
                motion_prompt.remove();
                motion_prompt = undefined;
            }
            self.last_axis_click = 'load';
            document.getElementById('status').innerHTML += "<br>" + "Loading Calibration";
            //self.clearAllButtonStates(); //Commenting it temporarily as it is not validated.
            OctoPrint.simpleApiCommand("autocal", "get_connection_status"); // Sequence start with checking connection.
        };

        self.onClickSelectZvCalBtn = function() {
            document.getElementById('status').innerHTML += '<br>' + 'Selected ZV';
            OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "zv"});
        }
        self.onClickSelectZvdCalBtn = function() {
            document.getElementById('status').innerHTML += '<br>' + 'Selected ZVD';
            OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "zvd"});
        }
        self.onClickSelectMzvCalBtn = function() {
           document.getElementById('status').innerHTML += '<br>' + 'Selected MZV';
           OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "mzv"});
        }
        self.onClickSelectEiCalBtn = function() {
           document.getElementById('status').innerHTML += '<br>' + 'Selected EI';
           OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "ei"});
        }
        self.onClickSelectEi2hCalBtn = function() {
           document.getElementById('status').innerHTML += '<br>' + 'Selected 2HEI';
           OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "ei2h"});
        }
        self.onClickSelectEi3hCalBtn = function() {
           document.getElementById('status').innerHTML += '<br>' + 'Selected 3HEI';
           OctoPrint.simpleApiCommand("autocal", "select_calibration_btn_click", {type: "ei3h"});
        }

        document.getElementById("vtolslider").oninput = function() { OctoPrint.simpleApiCommand("autocal", "vtol_slider_update", {val: vtolslider.value}); };

        self.onClickSaveCalibrationBtn = function() {
            document.getElementById('status').innerHTML += '<br>' + 'Saving Calibration';
            OctoPrint.simpleApiCommand("autocal", "save_calibration_btn_click");
        }

        self.onClickStartOverBtn = function() {
            if (confirm("Are you sure you want to start over?") == true) {
                document.getElementById('status').innerHTML = 'Reset Done successfully, Start again!!';
                OctoPrint.simpleApiCommand("autocal", "start_over_btn_click");
                // Delete all the graphs created
                Plotly.purge('acclrmtr_live_data_graph');
                Plotly.purge('calibration_results_graph');
                Plotly.purge('verification_results_graph');
                // Scroll to top of the document
                document.body.scrollTop = 0;
                document.documentElement.scrollTop = 0;
            }
            else {
                document.getElementById('status').innerHTML += '<br>' + 'Start Over Cancelled';
            }
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
        self.onBeforeBinding = function() {
            OctoPrint.simpleApiCommand("autocal", "get_layout_status");
            // self.newUrl(self.settings.settings.plugins.autocal.url());
            // self.newACCESS(self.settings.settings.plugins.autocal.ACCESSID());
			// self.newORG(self.settings.settings.plugins.autocal.ORG());
        }
    };

    // This is how our plugin registers itself with the application, by adding some configuration
    // information to the global variable OCTOPRINT_VIEWMODELS
    OCTOPRINT_VIEWMODELS.push([
        // This is the constructor to call for instantiating the plugin
        AutocalViewModel,

        // This is a list of dependencies to inject into the plugin, the order which you request
        // here is the order in which the dependencies will be injected into your view model upon
        // instantiation via the parameters argument
        ["settingsViewModel"],

        // Finally, this is the list of selectors for all elements we want this view model to be bound to.
        ["#tab_plugin_autocal"]
    ]);
});