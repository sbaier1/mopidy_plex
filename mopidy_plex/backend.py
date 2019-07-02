# -*- coding: utf-8 -*-

from __future__ import unicode_literals

from time import sleep

import pykka
import requests
from mopidy import backend, httpclient
from plexapi.myplex import MyPlexAccount
from plexapi.server import PlexServer

import mopidy_plex
from mopidy_plex import logger
from .library import PlexLibraryProvider
from .playback import PlexPlaybackProvider
from .playlists import PlexPlaylistsProvider


def get_requests_session(proxy_config, user_agent):
    proxy = httpclient.format_proxy(proxy_config)
    full_user_agent = httpclient.format_user_agent(user_agent)

    session = requests.Session()
    session.proxies.update({'http': proxy, 'https': proxy})
    session.headers.update({'user-agent': full_user_agent})

    return session


class PlexBackend(pykka.ThreadingActor, backend.Backend):
    def __init__(self, config, audio):
        super(PlexBackend, self).__init__(audio=audio)
        self.config = config
        self.session = get_requests_session(proxy_config=config['proxy'],
                                            user_agent='%s/%s' % (mopidy_plex.Extension.dist_name,
                                                                  mopidy_plex.__version__)
                                            )
        type = config['plex']['type']
        library = (config['plex']['library'])
        self.plex = None
        self.music = None
        if type == 'myplex':
            server = (config['plex']['server'])
            user = (config['plex']['username'])
            password = (config['plex']['password'])
            account = self.myplex_login(user, password)
            logger.info('Connecting to plex server: %s', server)
            self.plex = account.resource(server).connect(ssl=False)
            self.music = self.plex.library.section(library)
        elif type == 'direct':
            baseurl = (config['plex']['server'])
            token = (config['plex']['token'])
            self.plex = PlexServer(baseurl, token)
            self.music = self.plex.library.section(library)
        else:
            logger.error('Invalid value for plex backend type: %s', type)

        logger.info('Connected to plex server')
        logger.debug('Found music section on plex server %s: %s', self.plex, self.music)
        self.library_id = self.music.key
        self.uri_schemes = ['plex', ]
        self.library = PlexLibraryProvider(backend=self)
        self.playback = PlexPlaybackProvider(audio=audio, backend=self)
        self.playlists = PlexPlaylistsProvider(backend=self)

    def myplex_login(self, user, password):
        max_attempts = 20
        current_attempt = 0
        account = None
        while account is None:
            try:
                account = MyPlexAccount(user, password, session=self.session)
            except Exception as e:
                if current_attempt > max_attempts:
                    logger.error('Could not connect to MyPlex in time, exiting...')
                    return None
                logger.error(e)
                logger.error('Failed to log into MyPlex, retrying... %s/%s', current_attempt, max_attempts)
                sleep(5)
        return account

    def plex_uri(self, uri_path, prefix='plex'):
        '''Get a leaf uri and complete it to a mopidy plex uri.

        E.g. plex:artist:3434
             plex:track:2323
             plex:album:2323
             plex:playlist:3432
        '''
        uri_path = str(uri_path)
        if not uri_path.startswith('/library/metadata/'):
            uri_path = '/library/metadata/' + uri_path

        if uri_path.startswith('/library/metadata/'):
            uri_path = uri_path[len('/library/metadata/'):]
        return '{}:{}'.format(prefix, uri_path)

    def resolve_uri(self, uri_path):
        '''Get a leaf uri and return full address to plex server'''
        uri_path = str(uri_path)
        if not uri_path.startswith('/library/metadata/'):
            uri_path = '/library/metadata/' + uri_path
        return self.plex.url(uri_path)
