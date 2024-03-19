import os
import zipfile
from os.path import exists, join

import requests
from ovos_utils.log import LOG
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.auto_translatable import UniversalSkill
from pyfrotz import Frotz


def install_zork_data(destination_dir):
    """Install the zork data files in destination."""
    zork_data_dir = join(destination_dir, 'zork')
    try:
        os.mkdir(zork_data_dir)
    except FileExistsError:
        pass

    r = requests.get('http://www.infocom-if.org/downloads/zork1.zip',
                     stream=True)
    download_path = '/tmp/zork_data.zip'
    with open(download_path, 'wb') as fd:
        for chunk in r.iter_content(chunk_size=1024):
            fd.write(chunk)

    with zipfile.ZipFile(download_path, 'r') as zip_ref:
        zip_ref.extractall(zork_data_dir)


class ZorkInterpreter:
    def __init__(self, data, save_file):
        self.data = data
        self.save_file = save_file

        self.intro = "welcome to Zork"
        self.room = ""
        self.description = ""

        LOG.info('Starting Zork')
        self.game = Frotz(self.data)
        # Load default savegame
        if exists(self.save_file):
            LOG.info('Loading save game')
            self.restore(join(self.save_file))
        else:
            self.intro = self.game.get_intro()

    def save(self):
        """Save the game state."""
        self.game.save(self.save_file)

    def delete_save(self):
        if exists(self.save_file):
            os.remove(self.save_file)
            return True
        return False

    def restore(self, filename):
        """Restore saved game."""
        self.game.restore(filename)

    def cmd(self, action):
        """Write a command to the interpreter."""
        self.room, self.description = self.game.do_command(action)
        return self.room, self.description

    def look(self):
        """Read from zork interpreter process.

        Returns:
            (tuple) Room name, description.
        """
        self.room, self.description = self.game.do_command("look")
        return self.room, self.description


class ZorkSkill(UniversalSkill):

    def __init__(self, *args, **kwargs):
        # game is english only, apply bidirectional translation
        super().__init__(internal_language="en-us", *args, **kwargs)
        self.room = None
        self.playing = False
        self.zork = None

        self.data = join(self.file_system.path, 'zork/DATA/ZORK1.DAT')
        self.save_file = join(self.file_system.path, 'save.qzl')
        if not exists(self.data):
            self.log.info('Installing Zork data to %s', self.file_system.path)
            install_zork_data(self.file_system.path)

    @intent_handler(IntentBuilder('PlayZork').require('Play').require('Zork'))
    def play_zork(self, Message):
        """Starts zork and activates the converse part.

        Converse then handles the actual gameplay.
        """
        if not self.zork:
            self.zork = ZorkInterpreter(self.data, self.save_file)
            self.speak(self.zork.intro)
        room, description = self.zork.look()
        self.speak(description, expect_response=True)
        self.playing = True

    def leave_zork(self):
        self.speak_dialog('LeavingZork')
        self.playing = False
        self.zork.save()
        self.log.info('Zork savegame has been created')

    def converse(self, message) -> bool:
        """Pass sentence on to the frotz zork interpreter.

        The commands "quit" and "exit" will immediately exit the game.
        """
        utterances = message.data['utterances']
        if utterances:
            utterance = utterances[0]
            if self.playing:
                if "quit" in utterance or utterance == "exit":
                    self.leave_zork()
                    return True
                else:
                    # Send utterance to zork interpreter and then
                    # speak response
                    room, description = self.zork.cmd(utterance)
                    if not description:
                        room, description = self.zork.look()
                    self.speak(description, expect_response=True)
                    return True
        return False

    @intent_handler(
        IntentBuilder('DeleteSave').require('Delete').require('Zork').require('Save'))
    def delete_save(self, message):
        if self.zork.delete_save():
            self.speak_dialog('SaveDeleted')
        else:
            self.speak_dialog('NoSave')

    def stop(self) -> bool:
        """Stop playing."""
        if self.playing:
            self.leave_zork()
            return True
        return False
