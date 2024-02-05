/*
 * FilamentBuddy OctoPrint plugin
 * Copyright (C) 2024 Daniele Borgo
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */

$(function () {
    function FilamentBuddyViewModel(parameters) {
        let self = this;

        self.settingsViewModel = parameters[0];
        self.printerStateViewModel = parameters[1];
        self.temperatureViewModel = parameters[2];

        self.filamentbuddy = undefined;
        self.onBeforeBinding = function () {
            self.filamentbuddy = self.settingsViewModel.settings.plugins.filamentbuddy;
        };

        self.onAfterBinding = function () {
            if(self.filamentbuddy.first_startup()){
                self.filamentbuddy.first_startup(false);
                self.settingsViewModel.saveData();

                self.notify(
                    "This plugin needs to be configured in settings before using it.",
                    self.notifyType.notice
                );
            }

            // Filament changer
            self.server_fc_en(self.filamentbuddy.fc.en());
            self.filamentbuddy.fc.en.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.command_mode.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.command.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.force_cold.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.filament_length.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.filament_speed.subscribe(self.regenerateFilamentChanger)
            self.filamentbuddy.fc.target_x.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.target_y.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.z_hop.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.unload_command.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.load_command.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.use_unload.subscribe(self.regenerateFilamentChanger);
            self.filamentbuddy.fc.filament_length.subscribe(
                value => self.filamentbuddy.fc.filament_length(self.makeInteger(value))
            );
            self.filamentbuddy.fc.filament_speed.subscribe(
                value => self.filamentbuddy.fc.filament_speed(self.makeInteger(value))
            )
            self.filamentbuddy.fc.target_x.subscribe(
                value => self.filamentbuddy.fc.target_x(self.makeInteger(value))
            );
            self.filamentbuddy.fc.target_y.subscribe(
                value => self.filamentbuddy.fc.target_y(self.makeInteger(value))
            );
            self.filamentbuddy.fc.z_hop.subscribe(
                value => self.filamentbuddy.fc.z_hop(self.makeInteger(value))
            );
            self.filamentbuddy.fc.min_tool_temp.subscribe(
                value => self.filamentbuddy.fc.min_tool_temp(self.makeInteger(value))
            );
            self.regenerateFilamentChanger();

            // Filament sensor
            self.filamentbuddy.fs.polling_time.subscribe(
                value => self.filamentbuddy.fs.polling_time(self.makeInteger(value))
            );
            self.filamentbuddy.fs.run_out_time.subscribe(
                value => self.filamentbuddy.fs.run_out_time(self.makeInteger(value))
            );
            self.filamentbuddy.fs.mqtt_port.subscribe(
                value => self.filamentbuddy.fs.mqtt_port(self.makeInteger(value))
            );
            self.filamentbuddy.fs.en.subscribe(value => {
                self.stopUpdatingFilamentSensor();
                if(value)
                    self.updateFilamentStatus();
            });
            if(self.filamentbuddy.fs.en())
                self.updateFilamentStatus()

            // Filament remover
            self.filamentbuddy.fr.min_needed_temp.subscribe(
                value => self.filamentbuddy.fr.min_needed_temp(self.makeInteger((value)))
            );
            self.filamentbuddy.fr.retract_length.subscribe(
                value => self.filamentbuddy.fr.retract_length(self.makeInteger(value))
            );
            self.filamentbuddy.fr.extrude_length.subscribe(
                value => self.filamentbuddy.fr.extrude_length(self.makeInteger(value))
            );
        }

        self.sendGCode = (commands) => {
            let to_send = commands.split("\n").map(c => c.trim());
            OctoPrint.control.sendGcode(to_send);
            console.log("Sent: " + to_send.toString());
        }

        self.makeInteger = value => {
            try {
                let newValue = value.replace(/\D/g, '');
                return newValue ? newValue : "0";
            }
            catch(TypeError){
                return "0";
            }
        }

        self.notifyType = Object.freeze({
            notice: "notice",
            info: "info",
            success: "success",
            error: "error"
        })

        self.DEFAULT_NOTIFICATION_DURATION = 20_000; //ms
        self.ERROR_NOTIFICATION_DURATION = 120_000; //ms

        self.notify = (message, type = self.notifyType.info) => {
            new PNotify({
                type: type,
                title: "FilamentBuddy",
                text: message,
                delay: self.notifyType.error === type ?
                    self.ERROR_NOTIFICATION_DURATION : self.DEFAULT_NOTIFICATION_DURATION
            });
        }

        self.onDataUpdaterPluginMessage = (identifier, data) => {
            if("filamentbuddy" !== identifier)
                return;

            self.notify(data.message, data.is_severe ? self.notifyType.error : self.notifyType.notice);
        }

        self.askConfirmationBeforeExecuting = (message, toExecute) => {
            showConfirmationDialog({
                message: message,
                proceed: "Yes",
                cancel: "Cancel",
                nofade: true,
                onproceed: toExecute
            });
        }

        self.requireReset = (reset) => {
            self.askConfirmationBeforeExecuting(
                "This operation will reset this section.<br>Remember to save.",
                reset
            );
        }

        self.showInfo = (parameter) => {
            let split = parameter.split(".");
            let info = self.INFO[split[0]][split[1]];
            showMessageDialog({
                "title": info[0],
                "message": info[1]
            });
        }


        /***** FILAMENT CHANGER *****/

        self.server_fc_en = ko.observable();
        self.gen_unload_com = ko.observable();
        self.gen_load_com = ko.observable();

        self.regenerateFilamentChanger = () => {
            if(!self.filamentbuddy.fc.en()){
                self.gen_unload_com("-");
                self.gen_load_com("-");
                return;
            }

            if("simplified" === self.filamentbuddy.fc.command_mode()){
                if("m600" === self.filamentbuddy.fc.command()){
                    self.gen_unload_com("M600 X0 Y0");
                    self.gen_load_com("M600");
                    return;
                }

                if("g1" === self.filamentbuddy.fc.command()){
                    let c = self.filamentbuddy.fc.force_cold() ? "M302 P1\n" : "";
                    self.gen_unload_com(c + "G91\nG1 E-10\nG90");
                    self.gen_load_com(c + "G91\nG1 E10\nG90");
                    return;
                }

                self.gen_unload_com("M702");
                self.gen_load_com("M701");
                return;
            }

            if("complete" === self.filamentbuddy.fc.command_mode()){
                let length = self.filamentbuddy.fc.filament_length();
                let t_x = self.filamentbuddy.fc.target_x();
                let t_y = self.filamentbuddy.fc.target_y();
                let z_h = self.filamentbuddy.fc.z_hop();
                let s = self.filamentbuddy.fc.filament_speed();

                if("m600" === self.filamentbuddy.fc.command()){
                    self.gen_unload_com(
                        `M600 X0 Y0 L${-length} X${t_x} Y${t_y} Z${z_h}`
                    );
                    self.gen_load_com(`M600 L${length}`);
                    return;
                }

                if("g1" === self.filamentbuddy.fc.command()){
                    let c = self.filamentbuddy.fc.force_cold() ? "M302 P1\n" : "";
                    self.gen_unload_com(`${c}G91\nG1 E${-length} Z${z_h} F${s}\nG90`);
                    self.gen_load_com(`${c}G91\nG1 E${length} Z${-z_h} F${s}\nG90`);
                    return;
                }

                self.gen_unload_com(`M702 U${length} Z${z_h}`);
                self.gen_load_com(`M701 L${length}`);
                return;
            }

            self.gen_unload_com(self.filamentbuddy.fc.unload_command());
            self.gen_load_com(
                self.filamentbuddy.fc.use_unload() ?
                    self.filamentbuddy.fc.unload_command() :
                    self.filamentbuddy.fc.load_command()
            );
        }

        self.unloadFilament = () => {
            if(!self.filamentbuddy.fc.en())
                return;

            if(self.printerStateViewModel.isPrinting()){
                self.notify("Impossible to unload the filament while printing");
                return;
            }

            if(parseInt(self.filamentbuddy.fc.min_tool_temp()) >
                self.temperatureViewModel.temperatures.tool0.actual.at(-1)[1]){
                self.notify("Impossible to unload the filament since the tool temperature is too low");
                return;
            }

            self.regenerateFilamentChanger();
            self.sendGCode(self.gen_unload_com());
        }

        self.loadFilament = () => {
            if(!self.filamentbuddy.fc.en())
                return;

            // No need to check if the tool is hot
            if(self.printerStateViewModel.isPrinting()){
                self.notify("Impossible to load the filament while printing");
                return;
            }

            self.regenerateFilamentChanger();
            self.sendGCode(self.gen_load_com());
        }

        self.getAdditionalControls = () =>{
            if(!self.filamentbuddy.fc.en())
                return []

            return [
                {
                    "name": "FilamentBuddy: Filament Change",
                    "layout": "horizontal",
                    "type": "section",
                    "children": [
                        {
                            "name": "unload",
                            "javascript": self.unloadFilament
                        },
                        {
                            "name": "load",
                            "javascript": self.loadFilament
                        },
                        {
                            "name": "",
                            "additionalClasses": "fas fa-info-circle",
                            "javascript": () => { self.showInfo("fc.force_cold"); }
                        }
                    ]
                }
            ];
        }

        self.resetFilamentChanger = () => {
            self.requireReset(() => {
                let def = self.filamentbuddy.default;

                self.filamentbuddy.fc.en(def.fc.en());
                self.filamentbuddy.fc.command_mode(def.fc.command_mode());
                self.filamentbuddy.fc.command(def.fc.command());
                self.filamentbuddy.fc.force_cold(def.fc.force_cold());
                self.filamentbuddy.fc.filament_length(def.fc.filament_length());
                self.filamentbuddy.fc.filament_speed(def.fc.filament_speed());
                self.filamentbuddy.fc.target_x(def.fc.target_x());
                self.filamentbuddy.fc.target_y(def.fc.target_y());
                self.filamentbuddy.fc.z_hop(def.fc.z_hop());
                self.filamentbuddy.fc.unload_command(def.fc.unload_command());
                self.filamentbuddy.fc.load_command(def.fc.load_command());
                self.filamentbuddy.fc.use_unload(def.fc.use_unload());
                self.filamentbuddy.fc.min_tool_temp(def.fc.min_tool_temp());
                self.settingsViewModel.saveData();
            });
        }


        /***** FILAMENT SENSOR *****/

        self.is_filament_available = ko.observable();
        self.is_filament_error = ko.observable();
        self.is_filament_available(true);
        self.is_filament_error(true);
        self.fs_timeout = null;

        self.updateFilamentStatus = () => {
            $.ajax({
                url: API_BASEURL + "plugin/filamentbuddy",
                type: "POST",
                dataType: "json",
                contentType: "application/json; charset=UTF-8",
                data: JSON.stringify({
                    command: "filament_status"
                })
            }).done(function (data) {
                if(data['state'])
                    self.is_filament_available(data['filament']);
                self.is_filament_error(false);
            }).fail(function () {
                if(!self.is_filament_error())
                    self.notify("Error in retrieving filament status");
                self.is_filament_error(true);
            }).always(function () {
                if(self.filamentbuddy.fs.en()) //Just in case the plugin has been disabled while waiting for response
                    self.fs_timeout = setTimeout(
                        self.updateFilamentStatus,
                        self.filamentbuddy.fs.toolbar_time() * 1000
                    );
            });
        }

        self.stopUpdatingFilamentSensor = () => {
            if(self.fs_timeout != null) {
                clearTimeout(self.fs_timeout);
                self.fs_timeout = null;
            }
        }

        self.isMQTTPWShown = ko.observable(false);
        self.updateMQTTPasswordState = () => self.isMQTTPWShown(!self.isMQTTPWShown());

        self.testMQTTMessage = () => {
            self.askConfirmationBeforeExecuting(
                "If you have pending modifications, these will be automatically saved.",
                () => {
                    $.ajax({
                        url: API_BASEURL + "plugin/filamentbuddy",
                        type: "POST",
                        dataType: "json",
                        contentType: "application/json; charset=UTF-8",
                        data: JSON.stringify({
                            command: "test_mqtt"
                        })
                    }).done(function () {
                        console.log("MQTT command request received by the server");
                    }).fail(function () {
                        console.log("The server responded badly to the MQTT test");
                    });
                }
            );
        }

        self.resetFilamentSensor = () => {
            self.requireReset(() => {
                let def = self.filamentbuddy.default;

                self.filamentbuddy.fs.en(def.fs.en());
                self.filamentbuddy.fs.sensor_pin(def.fs.sensor_pin());
                self.filamentbuddy.fs.sensor_mode(def.fs.sensor_mode());
                self.filamentbuddy.fs.polling_time(def.fs.polling_time());
                self.filamentbuddy.fs.run_out_time(def.fs.run_out_time());
                self.filamentbuddy.fs.use_pause(def.fs.use_pause());
                self.filamentbuddy.fs.run_out_command(def.fs.run_out_command());
                self.filamentbuddy.fs.empty_voltage(def.fs.empty_voltage());
                self.filamentbuddy.fs.toolbar_time(def.fs.toolbar_time());
                self.filamentbuddy.fs.toolbar_en(def.fs.toolbar_en());
                self.settingsViewModel.saveData();
            });
        }

        self.resetFilamentSensorMQTTPart = () => {
            self.requireReset(() => {
                let def = self.filamentbuddy.default;

                self.filamentbuddy.fs.mqtt_en(def.fs.mqtt_en());
                self.filamentbuddy.fs.mqtt_address(def.fs.mqtt_address());
                self.filamentbuddy.fs.mqtt_port(def.fs.mqtt_port());
                self.filamentbuddy.fs.mqtt_client_id(def.fs.mqtt_client_id());
                self.filamentbuddy.fs.mqtt_use_login(def.fs.mqtt_use_login());
                self.filamentbuddy.fs.mqtt_username(def.fs.mqtt_username());
                self.filamentbuddy.fs.mqtt_password(def.fs.mqtt_password());
                self.filamentbuddy.fs.mqtt_topic(def.fs.mqtt_topic());
                self.filamentbuddy.fs.mqtt_message_string(def.fs.mqtt_message_string());
                self.settingsViewModel.saveData();
            });
        }


        /***** FILAMENT REMOVER *****/

        self.resetFilamentRemover = () => {
            self.requireReset(() => {
                let def = self.filamentbuddy.default;

                self.filamentbuddy.fr.en(def.fr.en());
                self.filamentbuddy.fr.hook_mode(def.fr.hook_mode())
                self.filamentbuddy.fr.min_needed_temp(def.fr.min_needed_temp())
                self.filamentbuddy.fr.command_mode(def.fr.command_mode());
                self.filamentbuddy.fr.retract_length(def.fr.retract_length());
                self.filamentbuddy.fr.extrude_length(def.fr.extrude_length());
                self.filamentbuddy.fr.force_cold(def.fr.force_cold());
                self.filamentbuddy.fr.retract_command(def.fr.retract_command());
                self.filamentbuddy.fr.extrude_command(def.fr.extrude_command());
                self.filamentbuddy.fr.use_unload(def.fr.use_unload());
                self.settingsViewModel.saveData();
            });
        }




        self.INFO = Object.freeze({
            "fc": {
                "command_mode": [
                    "Command mode",
                    "This parameter defines how the generation of Marlin G-code commands to send should be handled. " +
                    "The simplest way consist in just specifying which command the plugin has to use, the " +
                    "intermediate way allows to configure a bunch of their parameters and the most free way is to " +
                    "directly write the commands to run."
                ],
                "command": [
                    "G-code Command",
                    "This plugin support the automatic generation of three Marlin G-code commands: <i>G1</i>, " +
                    "<i>M600</i> and <i>M701</i>. This parameter is used to defined which of them needs to be used." +
                    "<br><br>Not all the printers supports these three commands but usually <i>G1</i> works."
                ],
                "force_cold":[
                    "Force cold extrusion",
                    "Some Marlin printers may have a check regarding the temperatures before moving the extruder with" +
                    "<i>G1</i> command. So if the nozzle temperature, or the bed one, are lower than a predefined " +
                    "threshold, the commands for the extruder are not executed. Since, in some cases the printer is " +
                    "still hot enough to perform these operations, it is possible to disable this check through the " +
                    "command <i>M302 P1</i>. This is enabled by a flag in this plugin settings, named <i>Force " +
                    "command</i>, which sends this Marlin command before moving the filament.<br><br>" +
                    "Properly evaluate the situation before turning on this flag."
                ],
                "filament_length": [
                    "Filament Length",
                    "This is the filament amount in millimeters to retract or to extrude when these commands are used."
                ],
                "filament_speed": [
                    "Filament speed",
                    "This is the filament speed in millimeter per minute when removed or automatically inserted."
                ],
                "target_xy": [
                    "Target x and y",
                    "These millimeters coordinates represent where the nozzle has to be placed when to perform " +
                    "these operations safely."
                ],
                "z_hop": [
                    "Z hop",
                    "This defines how much millimeters the z coordinate has to be moved to perform these operations."
                ],
                "min_tool_temp": [
                    "Minimum tool temperature",
                    "This is the minimum nozzle temperature, in Celsius degree, required to perform the commands. " +
                    "If the nozzle temperature is lower, no commands can be sent.<br>" +
                    "Some printer may refuse to run some extrusion movement commands if the nozzle or the bed are " +
                    "not enough hot, so it is discouraged to lower down this value."
                ],
            },
            "fs": {
                "sensor_pin": [
                    "BCM sensor pin",
                    "The filament sensor has to be connected to a Raspberry GPIO pin in order to inject its status " +
                    "in OctoPrint, and it is here defined. It requires to be in BCM format, so the one in which the " +
                    "name starts with <i>GPIO</i>.<br> This <a target='_blank' href='https://plugins.octoprint.org/" +
                    "plugins/gpiostatus/'>plugin</a> shows the GPIO and the pins names, but it can be selected " +
                    "with just the Raspberry documentation."
                ],
                "sensor_mode": [
                    "Sensor mode",
                    "Currently, there are two implemented methods to handle the filament sensor:<ul>" +
                    "<li><b>Polling</b>: this way periodically checks the filament availability;</li>" +
                    "<li><b>Interrupt</b>: this way checks only for changes in filament sensor pin, so it is " +
                    "executed only when the pin state changes.</li></ul>" +
                    "Both these methods suppose to have the pin permanently in a state when the filament is " +
                    "available and permanently in the other when it is not.<br>" +
                    "The plugin doesn't stop immediately the print when the filament becomes unavailable but wait " +
                    "for a user defined time to avoid errors."
                ],
                "polling_time": [
                    "Polling time",
                    "When polling, the plugin waits for a certain amount of time before repeating the filament " +
                    "availability check. This parameter is this time in seconds."
                ],
                "run_out_time": [
                    "Run out time",
                    "When the filament runs out, the plugin waits for this amount of time in seconds before actually " +
                    "stopping the printer. This avoid some cases in which the pin suddenly changes for a very short " +
                    "time its value due, for instance, to a loose connections."
                ],
                "run_out_com_pause": [
                    "Run out command and pause",
                    "This section defines what to do when the filament runs out. The checkbox specifies if the " +
                    "printer has to be placed in pause via OctoPrint while the textbox a G-code snippet to run. " +
                    "This organization allows, in case the user needs it, to stop the printer just via G-code, " +
                    "without passing via OctoPrint pausing feature."
                ],
                "empty_voltage": [
                    "Empty sensor voltage",
                    "The digital pin has two states, low and high. Some sensor uses high to communicate the filament " +
                    "availability while others uses low. This parameter defines the pin level when the filament <b>" +
                    "is not</b> inserted. By default, the plugin will pull the pin to this value, as indicated by " +
                    "the note below the selector."
                ],
                "toolbar_time": [
                    "Toolbar update time",
                    "The toolbar indicator is periodically updated with this parameter as interval. It is " +
                    "discouraged to use values lower than the one placed as default."
                ],
                "mqtt_en":[
                    "Enable MQTT run out message",
                    "This section allows to setup a simple MQTT notification when the filament runs out."
                ],
                "mqtt_addr_port":[
                    "MQTT address and port",
                    "These two parameters refer to the broker which is supposed to receive the message."
                ],
                "mqtt_id":[
                    "MQTT client ID",
                    "This string identifies the sender, in this case OctoPrint, in particular this plugin."
                ],
                "mqtt_auth":[
                    "MQTT authentication",
                    "This plugin supports both the brokers without authentications and the ones who need a pair of " +
                    "username and password."
                ],
                "mqtt_topic":[
                    "MQTT topic",
                    "This is the topic in which the plugin has to send the message."
                ],
                "mqtt_message_string":[
                    "MQTT message",
                    "This is the message the plugin has to send to the broker."
                ]
            },
            "fr": {
                "hook_mode": [
                    "Hook mode",
                    "The filament can be inserted or removed in several different occasions. This plugin supports " +
                    "two options:<ul>" +
                    "<li>The insertion is performed before starting the G-code file and it is removed after its last " +
                    "instruction.</li>" +
                    "<li>The insertion is performed as soon as the nozzle becomes enough hot and removed when the " +
                    "nozzle target temperature is set to 0°C.</li></ul><br><br>" +
                    "Note that the second option consists in injecting G-code during a print so two conditions must " +
                    "be satisfied: the nozzle has to wait for the first warming procedure (usually done by the " +
                    "command <i>M109</i>) and the printer has to set its nozzle temperature to zero Celsius degree " +
                    "when done. Luckly these conditions are usually always satisfied, so no problems should occur."
                ],
                "min_needed_temp": [
                    "Minimum insertion tool temperature",
                    "When the <i>Hook mode</i> is set to bound to temperature, this is the minimum one in Celsius " +
                    "degrees at which the filament insertion is performed."
                ],
                "command_mode": [
                    "Command mode",
                    "This selector defines if the user prefers to use suggested command or to write a proper G-code " +
                    "snippet to perform this operation."
                ],
                "length": [
                    "Extrusion and retraction length",
                    "These lengths represents how much filament in millimeters has to be removed or inserted when " +
                    "the print ends or starts."
                ]
            }
        })
    }

    OCTOPRINT_VIEWMODELS.push({
        construct: FilamentBuddyViewModel,
        dependencies: ["settingsViewModel", "printerStateViewModel", "temperatureViewModel"],
        elements: ["#settings_plugin_filamentbuddy", "#navbar_plugin_filamentbuddy"]
    });
});
