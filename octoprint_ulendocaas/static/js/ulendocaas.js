$(function () {
    function UlendoCaasViewModel(parameters) {
        var self = this;
        self.settings = parameters[0];
        self.last_axis_click = 'unknown';

        const photoInput = document.getElementById('photoupload');
        const fileChosen = document.getElementById('file-chosen');
        const uploadButton = document.getElementById('upload_image_btn');
        const previewContainer = document.getElementById('preview-container');
        const previewImage = document.getElementById('preview-image');
        const imageRatingLabel = document.getElementById('rating-label');
        const imageRating = document.getElementById("image-rating");
        const progressOutput = document.getElementById("progress-output");

        photoInput.addEventListener('change', function () {
            uploadButton.disabled = true;
            if (this.files && this.files[0]) {
                const file = this.files[0];
                if (file.type.startsWith('image/')) {
                    fileChosen.textContent = file.name;
                    imageRatingLabel.style.display = 'block';

                    const reader = new FileReader();
                    reader.onload = function (e) {
                        previewImage.src = e.target.result;
                        previewContainer.style.display = 'block';
                    };
                    reader.readAsDataURL(file);
                } else {
                    fileChosen.textContent = 'Please select an image file.';
                    imageRatingLabel.style.display = 'none';
                }
            }
        })

        imageRatingLabel.addEventListener('change', function () {
            uploadButton.disabled = false;
        })

        self.clearAllButtonStates = function () {
            // Reset the state of accelerometer button
            acclrmtr_connect_btn.className = "acclrmtr_connect_btn btn";
            const calibrate_x_status_label = document.getElementById('calibrate_x_status_label');
            const calibrate_y_status_label = document.getElementById('calibrate_y_status_label');
            const calibration_instructions = document.getElementById('calibration_instructions');
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


        self.onAccelerometerDataPlotClick = function (data) {
            var xval = data.points[0].x;
            var update = {
                shapes: [{type: 'line',
                    x0: xval, y0: 0, x1: xval, y1: 1, xref: 'x', yref: 'paper',
                    line: {color: 'red',width: 2}
                }]
            };
            
            Plotly.relayout('accelerometer_data_graph', update);

            document.getElementById('accelerometer_data_graph_container').classList.remove('pulse');
            
            OctoPrint.simpleApiCommand("ulendocaas", "on_accelerometer_data_plot_click", { xval: xval });
        }
        
        
        self.onDataUpdaterPluginMessage = function (plugin, data) {
            if (plugin != "ulendocaas") { return; }


            if (data.type == "accelerometer_data") {
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
                Plotly.newPlot('accelerometer_data_graph', [series1], layout, config);
                if (data.prompt_user) {
                    document.getElementById('accelerometer_data_graph').on('plotly_click', self.onAccelerometerDataPlotClick);
                    document.getElementById('accelerometer_data_graph_container').classList.add('pulse');
                } else {
                    document.getElementById('accelerometer_data_graph_container').classList.remove('pulse');
                }
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
            
                if (data.reset_sliders) {
                    document.getElementById("damping_slider").value = 100;
                    document.getElementById("damping_slider_value").innerText = document.getElementById("damping_slider").value/10;
                    document.getElementById("vtol_slider").value = 5;
                    document.getElementById("vtol_slider_value").innerText = document.getElementById("vtol_slider").value;
                }
            
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
                const calibrate_x_status_label = document.getElementById('calibrate_x_status_label');
                const calibrate_y_status_label = document.getElementById('calibrate_y_status_label');
                const calibration_instructions = document.getElementById('calibration_instructions');
                const license_status = document.getElementById('license_status');
                const license_status_message = document.getElementById('license_status_message');

                acclrmtr_connect_btn.classList.add("".concat(data.acclrmtr_connect_btn_state, "_style"));
                calibrate_x_axis_btn.classList.add("".concat(data.calibrate_x_axis_btn_state, "_style"));
                calibrate_y_axis_btn.classList.add("".concat(data.calibrate_y_axis_btn_state, "_style"));

                if (data.is_active_client) {
                    self.removeClass(license_status, "alert-");
                    license_status.classList.add("alert-success");
                    license_status.classList.add("alert-block");
                    license_status_message.innerText = "Credentials Verified";
                } else {
                    self.removeClass(license_status, "alert-");
                    license_status.classList.add("alert-warning");
                    license_status.classList.add("alert-block");
                    license_status_message.innerText = "Invalid Credentials (Check your ORG, ACCESSID and MACHINEID) ";
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
                } else {
                    calibrate_x_axis_btn.style.display = "none";
                    calibrate_y_axis_btn.style.display = "none";
                }

                calibrate_select_btn_group_id.style.display = "none";
                save_calibration_btn.style.display = "none";
                if (data._state == 'NOTCALIBRATED') { calibrate_x_axis_btn.innerText = 'Calibrate X'; }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATING') {
                    let message = "Calibrating";
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_x_status_label.classList.add("label-warning");
                    calibrate_x_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit";
                }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONREADY') {
                    let message = "Ready";
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_select_btn_group_id.style.display = "inline-block";
                    calibrate_x_status_label.classList.add("label-info");
                    calibrate_x_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit";
                    calibration_instructions.style.display = "block";
                }
                else if (data.calibrate_x_axis_btn_state == 'CALIBRATIONAPPLIED') {
                    let message = "Calibrated";
                    save_calibration_btn.style.display = "block";
                    self.removeClass(calibrate_x_status_label, "label-");
                    calibrate_x_status_label.classList.add("label-success");
                    calibrate_x_status_label.innerText = message;
                    calibrate_x_status_label.style.visibility = "inherit"; //inherits parent style
                    calibration_instructions.style.display = "block";
                }

                if (data.calibrate_y_axis_btn_state == 'NOTCALIBRATED') { calibrate_y_axis_btn.innerText = 'Calibrate Y'; }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATING') {
                    let message = "Calibrating";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_y_status_label.classList.add("label-warning");
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONREADY') {
                    let message = "Ready";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_select_btn_group_id.style.display = "inline-block";
                    calibrate_y_status_label.classList.add("label-info");
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                    calibration_instructions.style.display = "block";
                }
                else if (data.calibrate_y_axis_btn_state == 'CALIBRATIONAPPLIED') {
                    let message = "Calibrated";
                    save_calibration_btn.style.display = "block";
                    self.removeClass(calibrate_y_status_label, "label-");
                    calibrate_y_status_label.classList.add("label-success");
                    calibrate_y_status_label.innerText = message;
                    calibrate_y_status_label.style.visibility = "inherit";
                    calibration_instructions.style.display = "block";
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

                if (data.damping_slider_visible) {
                    document.getElementById("damping_group").style.display = 'flex';
                    document.getElementById("damping_slider_value").innerText = document.getElementById("damping_slider").value/10;
                }
                else document.getElementById("damping_group").style.display = 'none';

                if (data.vtol_slider_visible) {
                    document.getElementById("vtol_group").style.display = 'flex';
                    document.getElementById("vtol_slider_value").innerText = document.getElementById("vtol_slider").value;
                }
                else document.getElementById("vtol_group").style.display = 'none';

                if (!data.damping_slider_visible && !data.vtol_slider_visible) {
                    document.getElementById('share_data_to_enable_sliders_element').style.display = 'none';
                }

                if (data.enable_controls_by_data_share) {
                    document.getElementById('share_data_to_enable_sliders_element').style.display = 'none';

                    document.getElementById('damping_slider').disabled = false;
                    document.getElementById('damping_slider').style.opacity = '1.0';
                    document.getElementById('damping_slider').style.pointerEvents = 'auto';
                    
                    document.getElementById('vtol_slider').disabled = false;
                    document.getElementById('vtol_slider').style.opacity = '1.0';
                    document.getElementById('vtol_slider').style.pointerEvents = 'auto';
                    
                }
                else {
                    if (data.damping_slider_visible || data.vtol_slider_visible) {
                        document.getElementById('share_data_to_enable_sliders_element').style.display = 'block';
                    }

                    document.getElementById('damping_slider').disabled = true;
                    document.getElementById('damping_slider').style.opacity = '0.5';
                    document.getElementById('damping_slider').style.pointerEvents = 'none';

                    document.getElementById('vtol_slider').disabled = true;
                    document.getElementById('vtol_slider').style.opacity = '0.5';
                    document.getElementById('vtol_slider').style.pointerEvents = 'none';
                }

                if (data.mode == 'manual') {
                    document.getElementById('calibrate_input_shaping_tips').textContent = 'Use the acceleration data graph to set the frequency to the strongest'
                                                                                          + ' acceleration measured, then select an input shaping option below. Use'
                                                                                          + ' the sliders below to set damping and vibration tolerance if desired.'
                }
                else {
                    document.getElementById('calibrate_input_shaping_tips').textContent = 'Select an input shaping option below. The input shaper\'s'
                                                                                          + ' frequency and damping will be automatically optimized.'
                                                                                          + ' For EI type shapers, adjust the vibration tolerance if desired.'
                }

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

            if (data.type == "close_popups") {
                PNotify.removeAll();
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

        document.getElementById("damping_slider").oninput = function () {
            document.getElementById("damping_slider_value").innerText = damping_slider.value/10;
            OctoPrint.simpleApiCommand("ulendocaas", "damping_slider_update", { val: damping_slider.value });
        };

        document.getElementById("vtol_slider").oninput = function () {
            document.getElementById("vtol_slider_value").innerText = vtol_slider.value;
            OctoPrint.simpleApiCommand("ulendocaas", "vtol_slider_update", { val: vtol_slider.value });
        };

        self.onClickSaveCalibrationBtn = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "save_calibration_btn_click");
        }

        self.onClickUploadImageBtn = function () {
            var files = photoInput.files;
            if (!files.length) {
                return alert("Please choose a file to upload first.");
            }
            var file = files[0];
            var ratingValue = imageRating.value;
            
            // Read and process the image file
            var reader = new FileReader();
            reader.readAsArrayBuffer(file); // Start reading the file

            reader.onload = function (event) {
                var blob = new Blob([event.target.result]); // Create blob
                window.URL = window.URL || window.webkitURL;
                var blobURL = window.URL.createObjectURL(blob); // and get it's URL
                
                var image = new Image();
                image.src = blobURL;

                image.onload = async function () {
                    // Resize the image once it's loaded
                    var resizedFile = resizeMe(image); // Resize image using canvas
                    var settings = self.settings.settings.plugins.ulendocaas;
                    var org_id = settings.ORG();
                    var access_id = settings.ACCESSID();
                    var machine_id = settings.MACHINEID();
                    var machine_name = settings.MACHINENAME();

                    try{
                        const response = await fetch('https://loc6hkp2pk.execute-api.us-east-2.amazonaws.com/beta/solve', {
                            method: "POST",
                            body: JSON.stringify({ 
                                'ACTION': 'UPDATE',
                                'TASK': 'UPLOAD_IMAGE', 
                                'RATING': ratingValue,     
                                'IMAGE_B64': resizedFile,        
                                'ACCESS':{
                                    'CLIENT_ID': org_id,
                                    'ACCESS_ID': access_id,
                                    'MACHINE_ID': machine_id,
                                    'MACHINE_NAME': machine_name
                                },
                                'RATING': ratingValue 
                            }),
                          });
                        
                        new PNotify({
                            title: 'Feedback has been sent.',
                            text: 'Thank you for your feedback.',
                            type: 'success',
                            hide: true
                        });
                        if (!response.ok) {
                            new PNotify({
                                title: 'There was an error sending feedback.',
                                text: 'Please try again later.',
                                type: 'error',
                                hide: true
                            });
                            throw new Error('Network response was not ok');
                        
                        }
                    } catch (error) {
                        new PNotify({
                            title: 'There was an error sending feedback.',
                            text: 'Please try again later.',
                            type: 'error',
                            hide: true
                        });
                        console.error('Error:', error);
                    }
                };
            };
        };

        const resizeMe = function (img, max_width = 500, max_height = 500) {

            var canvas = document.createElement('canvas');

            var width = img.width;
            var height = img.height;

            // calculate the width and height, constraining the proportions
            if (width > height) {
                if (width > max_width) {
                    //height *= max_width / width;
                    height = Math.round(height *= max_width / width);
                    width = max_width;
                }
            } else {
                if (height > max_height) {
                    //width *= max_height / height;
                    width = Math.round(width *= max_height / height);
                    height = max_height;
                }
            }

            // resize the canvas and draw the image data into it
            canvas.width = width;
            canvas.height = height;
            var ctx = canvas.getContext("2d");
            ctx.drawImage(img, 0, 0, width, height);

            return canvas.toDataURL("image/png", 0.7); // get the data from canvas as 70% JPG (can be also PNG, etc.)

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
                                Plotly.purge('accelerometer_data_graph');
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

        self.onSettingsHidden = function () {
            OctoPrint.simpleApiCommand("ulendocaas", "on_settings_close")
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
        };
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
        elements: ["#tab_plugin_ulendocaas"]
    });
});
