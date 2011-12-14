#!/usr/bin/env python

# Copyright (c) 2011, Dorian Scholz, TU Darmstadt
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above
#     copyright notice, this list of conditions and the following
#     disclaimer in the documentation and/or other materials provided
#     with the distribution.
#   * Neither the name of the TU Darmstadt nor the names of its
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import division
import os

from rosgui.QtBindingHelper import loadUi
from QtCore import Qt, QTimer, Slot
from QtGui import QDockWidget, QIcon, QMenu, QTreeWidgetItem

import roslib
roslib.load_manifest('rosgui_topic')
import rospy
import TopicInfo
reload(TopicInfo) # force reload to update on changes during runtime


# main class inherits from the ui window class
class TopicWidget(QDockWidget):
    _column_names = ['topic', 'type', 'bandwidth', 'rate', 'value']

    def __init__(self, plugin, plugin_context):
        super(TopicWidget, self).__init__(plugin_context.main_window())
        ui_file = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'TopicWidget.ui')
        loadUi(ui_file, self)
        self._plugin = plugin

        self._current_topic_list = []
        self._topic_infos = {}
        self._tree_items = {}
        self._column_index = {}
        for column_name in self._column_names:
            self._column_index[column_name] = len(self._column_index)

        self.refresh_topics()
        # init and start update timer
        self._timer_refresh_topics = QTimer(self)
        self._timer_refresh_topics.timeout.connect(self.refresh_topics)
        self._timer_refresh_topics.start(1000)


    @Slot()
    def refresh_topics(self):
        # fill tree view
        topic_list = rospy.get_published_topics()
        if self._current_topic_list != topic_list:
            self._current_topic_list = topic_list

            # start new topic dict
            self.topics_tree_widget.clear()
            new_topic_infos = {}

            for topic_name, message_type in sorted(topic_list):
                # if topic is new
                if topic_name not in self._topic_infos:
                    # create new TopicInfo
                    topic_info = TopicInfo.TopicInfo(topic_name)
                    # if successful add it to the dict
                    if topic_info._topic_name:
                        new_topic_infos[topic_name] = topic_info
                else:
                    # if topic has been seen before, copy it to new dict and remove it form the old one
                    new_topic_infos[topic_name] = self._topic_infos[topic_name]
                    del self._topic_infos[topic_name]

                # if TopicInfo exist for topic, add it to tree view
                if topic_name in new_topic_infos:
                    self._recursive_create_widget_items(self.topics_tree_widget, topic_name, message_type, new_topic_infos[topic_name].message_class())

            # stop monitoring and delete non existing topics
            for topic_info in self._topic_infos.values():
                topic_info.stop_monitoring()
                del topic_info

            # change to new topic dict
            self._topic_infos = new_topic_infos


        for topic_info in self._topic_infos.values():
            if topic_info.monitoring:
                # update rate
                rate, _, _, _ = topic_info.get_hz()
                rate_text = '%1.2f' % rate if rate != None else 'unknown'

                # update bandwidth
                bytes_per_s, _, _, _ = topic_info.get_bw()
                if bytes_per_s is None:
                    bandwidth_text = 'unknown'
                elif bytes_per_s < 1000:
                    bandwidth_text = '%.2fB/s' % bytes_per_s
                elif bytes_per_s < 1000000:
                    bandwidth_text = '%.2fKB/s' % (bytes_per_s / 1000.)
                else:
                    bandwidth_text = '%.2fMB/s' % (bytes_per_s / 1000000.)

                # update values
                value_text = ''
                self.update_value(topic_info._topic_name, topic_info.last_message)

            else:
                rate_text = ''
                bandwidth_text = ''
                value_text = 'not monitored'

            self._tree_items[topic_info._topic_name].setText(self._column_index['rate'], rate_text)
            self._tree_items[topic_info._topic_name].setText(self._column_index['bandwidth'], bandwidth_text)
            self._tree_items[topic_info._topic_name].setText(self._column_index['value'], value_text)


        # resize columns
        for i in range(self.topics_tree_widget.columnCount()):
            self.topics_tree_widget.resizeColumnToContents(i)

        # limit width of value column
        current_width = self.topics_tree_widget.columnWidth(self._column_index['value'])
        self.topics_tree_widget.setColumnWidth(self._column_index['value'], min(150, current_width))


    def update_value(self, topic_name, message):
        if hasattr(message, '__slots__'):
            for slot_name in message.__slots__:
                self.update_value(topic_name + '/' + slot_name, getattr(message, slot_name))

        elif type(message) in (list, tuple) and (len(message) > 0) and hasattr(message[0], '__slots__'):
            for index, slot in enumerate(message):
                if topic_name + '[%d]' % index in self._tree_items:
                    self.update_value(topic_name + '[%d]' % index, slot)
                else:
                    base_type_str, _ = self._extract_array_info(self._tree_items[topic_name].text(self._column_index['type']))
                    self._recursive_create_widget_items(self._tree_items[topic_name], topic_name + '[%d]' % index, base_type_str, slot)

        else:
            if topic_name in self._tree_items:
                self._tree_items[topic_name].setText(self._column_index['value'], repr(message))


    def _extract_array_info(self, type_str):
        array_size = None
        if '[' in type_str and type_str[-1] == ']':
            type_str, array_size_str = type_str.split('[', 1)
            array_size_str = array_size_str[:-1]
            if len(array_size_str) > 0:
                array_size = int(array_size_str)
            else:
                array_size = 0

        return type_str, array_size


    def _recursive_create_widget_items(self, parent, topic_name, type_name, message):
        if parent is self.topics_tree_widget:
            # show full topic name with preceding namespace on toplevel item
            topic_text = topic_name
        else:
            topic_text = topic_name.split('/')[-1]
            if '[' in topic_text:
                topic_text = topic_text[topic_text.index('['):]
        item = QTreeWidgetItem(parent)
        item.setText(self._column_index['topic'], topic_text)
        item.setText(self._column_index['type'], type_name)
        item.setData(0, Qt.UserRole, topic_name)
        self._tree_items[topic_name] = item
        if hasattr(message, '__slots__') and hasattr(message, '_slot_types'):
            for slot_name, type_name in zip(message.__slots__, message._slot_types):
                self._recursive_create_widget_items(item, topic_name + '/' + slot_name, type_name, getattr(message, slot_name))

        else:
            base_type_str, array_size = self._extract_array_info(type_name)
            try:
                base_instance = roslib.message.get_message_class(base_type_str)()
            except ValueError:
                base_instance = None
            if array_size is not None and hasattr(base_instance, '__slots__'):
                for index in range(array_size):
                    self._recursive_create_widget_items(item, topic_name + '[%d]' % index, base_type_str, base_instance)


    @Slot('QPoint')
    def on_topics_tree_widget_customContextMenuRequested(self, pos):
        item = self.topics_tree_widget.itemAt(pos)
        if item is None:
            return

        # show context menu
        menu = QMenu(self)
        actionToggleMonitoring = menu.addAction(QIcon.fromTheme('search'), "Toggle Monitoring")
        action_item_expand = menu.addAction(QIcon.fromTheme('zoom-in'), "Expand All Children")
        action_item_collapse = menu.addAction(QIcon.fromTheme('zoom-out'), "Collapse All Children")
        action = menu.exec_(self.topics_tree_widget.mapToGlobal(pos))

        # evaluate user action
        if action is actionToggleMonitoring:
            root_item = item
            while root_item.parent() is not None:
                root_item = root_item.parent()
            root_topic_name = root_item.data(0, Qt.UserRole)
            self._topic_infos[root_topic_name].toggle_monitoring()

        elif action in (action_item_expand, action_item_collapse):
            expanded = (action is action_item_expand)
            def recursive_set_expanded(item):
                item.setExpanded(expanded)
                for index in range(item.childCount()):
                    recursive_set_expanded(item.child(index))
            recursive_set_expanded(item)


    # override Qt's closeEvent() method to trigger _plugin unloading
    def closeEvent(self, event):
        for topic_info in self._topic_infos.values():
            topic_info.stop_monitoring()
        self._timer_refresh_topics.stop()
        event.ignore()
        self._plugin.deleteLater()
