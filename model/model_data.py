import random
import re

from bpy.props import IntProperty, StringProperty, BoolProperty

from utilities.console import console_print
from .. import global_data


def extract_last_bracket_number(text):
    match = re.search(r'\[(\d+)\](?!.*\[)', text)
    if match:
        return int(match.group(1))
    return None


class ModelData:
    """Defines temporary data that can be used in the current session and will not be saved in file."""
    name: StringProperty(name="name", )
    global_idx: IntProperty(
        name="global idx", default=-1, options={"HIDDEN"}
    )
    global_uuid: IntProperty(
        name="global uuid", default=-1, options={"HIDDEN"}
    )

    def get_temp_data(self) -> dict:
        temp_data = global_data.temp_data
        if 0 <= self.global_idx < len(temp_data):
            data = temp_data[self.global_idx]
            if "uuid" in data and data["uuid"] == self.global_uuid:
                return data

        temp_data.append({})
        self.global_idx = len(temp_data) - 1
        data = temp_data[self.global_idx]
        if self.global_uuid == -1 or (
                self.global_uuid in global_data.uuid2obj and global_data.uuid2obj[self.global_uuid] != self):
            self.global_uuid = random.randint(-2_147_483_647, 2_147_483_647)
            # console_print("new global uuid ", self.global_uuid)
            while self.global_uuid in global_data.uuid2obj:
                self.global_uuid = random.randint(-2_147_483_647, 2_147_483_647)
        global_data.uuid2obj[self.global_uuid] = self
        data["uuid"] = self.global_uuid
        return data

    def get_temp_data_item(self, name: str, default=None):
        temp_data = self.get_temp_data()
        if name not in temp_data:
            if callable(default):
                default = default()
            temp_data[name] = default
        return temp_data[name]

    def set_temp_data_item(self, name: str, value):
        temp_data = self.get_temp_data()
        temp_data[name] = value

    def clear_temp_data(self):
        pass

    @classmethod
    def refresh_collection_uuid(cls, coll):
        for obj in coll:
            global_data.uuid2obj[obj.global_uuid] = obj

    def try_regain_self(self):
        pass

    def get_index(self):
        return extract_last_bracket_number(self.path_from_id())


def define_temp_prop(cls, name, default=None):
    @property
    def func(self):
        return self.get_temp_data_item(name, default)

    setattr(cls, name, func)

    @func.setter
    def setter(self, value):
        self.set_temp_data_item(name, value)

    setattr(cls, name, setter)


class Selectable:
    is_selected: BoolProperty(
        name="isSelected", default=False,
    )

