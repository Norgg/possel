#!/usr/bin/env python
# -*- coding: utf-8 -*-
import argparse
import collections
import logging

from pircel import tornado_adapter

from possel import model

logger = logging.getLogger(__name__)


COMMANDS = {'join',
            'part',
            'query',
            'me',
            'nick',
            'connect',
            'disconnect',
            'help',
            }


def build_prefix_map(strings):
    out = collections.defaultdict(list)
    for string in strings:
        prefix = ''
        for char in string:
            prefix += char
            out[prefix].append(string)
    return out

PREFIX_COMMANDS = build_prefix_map(COMMANDS)


class CommandParser(argparse.ArgumentParser):
    def parse_args(self, buffer, args_or_empty_list, *args, **kwargs):
        self.buffer = buffer
        try:
            split_args = args_or_empty_list[0].split()
        except IndexError:
            split_args = []
        return super(CommandParser, self).parse_args(split_args, *args, **kwargs)

    def _print_message(self, message, unused_file=None):
        buffer = self.buffer
        model.create_line(buffer=buffer, content='=' * 80, kind='other', nick=model.SYSNICK)
        for line in message.splitlines():
            model.create_line(buffer=buffer, content=line, kind='other', nick=model.SYSNICK)
        model.create_line(buffer=buffer, content='=' * 80, kind='other', nick=model.SYSNICK)

    def exit(self, *args, **kwargs):
        raise ValueError()

    def decorate(self, function):
        def inner_function(instance, buffer, args_or_empty_list):
            try:
                args = self.parse_args(buffer, args_or_empty_list)
            except ValueError:
                pass
            else:
                args.buffer = buffer
                function(instance, args)

        inner_function.parser = self
        return inner_function


help_parser = CommandParser(prog='help', description='Display help and usage information for commands')
help_parser.add_argument('command', help='The command to display help for', choices=COMMANDS)


join_parser = CommandParser(prog='join', description='Join a new channel')
join_parser.add_argument('channel', help='The channel to join')
join_parser.add_argument('password', default=None, nargs='?',
                         help='Optional password for the channel')

part_parser = CommandParser(prog='part', description='Leave a channel')
part_parser.add_argument('channel', help='The channel to leave', default=None, nargs='?')


query_parser = CommandParser(prog='query', description='Start a private conversation')
query_parser.add_argument('who', help='Who to start a conversation with')


nick_parser = CommandParser(prog='query', description='Change your nickname on this server')
nick_parser.add_argument('new_nick', help='What to change your nick to')

me_parser = CommandParser(prog='me', description='Do a thing!')
me_parser.add_argument('action', help='The thing to do', nargs=argparse.REMAINDER)


connect_parser = CommandParser(prog='connect', description='Connect to a new IRC server')
connect_parser.add_argument('-i', '--insecure', action='store_true',
                            help='Disable ssl/tls for this server')
connect_parser.add_argument('-p', '--port', default=6697,
                            help='The port to connect on')
connect_parser.add_argument('-n', '--nick', default=None,
                            help='The nick to use on this server')
connect_parser.add_argument('-r', '--realname', default=None,
                            help='The real name to use on this server')
connect_parser.add_argument('-u', '--username', default=None,
                            help='The username to use on this server')
connect_parser.add_argument('host', help='The server to connect to')


disconnect_parser = CommandParser(prog='disconnect', description='Disconnect from the current IRC server')
disconnect_parser.add_argument('message', help='The quit message', nargs=argparse.REMAINDER)


class Dispatcher:
    def __init__(self, interfaces):
        self.interfaces = interfaces

    def dispatch(self, buffer_id, line):
        if line.startswith('/'):
            line = line[1:]
        command, *rest = line.split(maxsplit=1)
        command = command.lower()

        if command in PREFIX_COMMANDS:
            buffer = model.IRCBufferModel.get(id=buffer_id)
            if len(PREFIX_COMMANDS[command]) == 1:
                actual_command, = PREFIX_COMMANDS[command]
                getattr(self, actual_command)(buffer, rest)
            else:
                model.create_line(buffer=buffer,
                                  content='ambiguous command "{}"'.format(command),
                                  kind='other',
                                  nick=model.SYSNICK)

    @help_parser.decorate
    def help(self, args):
        parser = getattr(self, args.command).parser
        parser.buffer = args.buffer
        parser.print_help()

    @join_parser.decorate
    def join(self, args):
        if args.channel is None:
            args.channel = args.buffer.name
        interface = self.interfaces[args.buffer.server.id]
        interface.server_handler.join(args.channel, args.password)

    @part_parser.decorate
    def part(self, args):
        if args.channel is None:
            args.channel = args.buffer.name
        interface = self.interfaces[args.buffer.server.id]
        interface.server_handler.part(args.channel)

    @query_parser.decorate
    def query(self, args):
        model.ensure_buffer(args.who, args.buffer.server)

    def me(self, buffer, rest):
        line = rest[0]
        interface = self.interfaces[buffer.server.id]
        interface.server_handler.send_message(buffer.name, '\1ACTION {}\1'.format(line))

    # Doesn't actually use the parser but we want /help to work
    me.parser = me_parser

    @nick_parser.decorate
    def nick(self, args):
        interface = self.interfaces[args.buffer.server.id]
        interface.server_handler.change_nick(args.new_nick)

    @connect_parser.decorate
    def connect(self, args):
        if None in {args.nick, args.realname, args.username}:
            user = args.buffer.server.user
        server = model.create_server(host=args.host,
                                     port=args.port,
                                     secure=not args.insecure,
                                     nick=args.nick or user.nick,
                                     realname=args.realname or user.realname,
                                     username=args.username or user.username)

        interface = model.IRCServerInterface(server)
        tornado_adapter.IRCClient.from_interface(interface).connect()
        self.interfaces[interface.server_model.id] = interface

    @disconnect_parser.decorate
    def disconnect(self, args):
        if args.buffer.server:
            model.create_line(buffer=args.buffer, content="*** DISCONNECTED ***", kind='other', nick=model.SYSNICK)
            model.disconnect(args.buffer.server)
            interface = self.interfaces[args.buffer.server.id]
            interface.server_handler.quit("quit")
        else:
            model.create_line(buffer=buffer,
                              content="Can't disconnect from system buffer.",
                              kind='other',
                              nick=model.SYSNICK)


def main():
    pass

if __name__ == '__main__':
    main()
