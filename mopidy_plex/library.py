# -*- coding: utf-8 -*-

from __future__ import print_function
from __future__ import unicode_literals

import urllib

from mopidy import backend
from mopidy.models import Artist, Album, SearchResult, Track, Ref
from plexapi import audio as plexaudio
from plexapi import utils as plexutils

import re

from mopidy_plex import logger
from .mwt import MWT

from functools import reduce


class PlexLibraryProvider(backend.LibraryProvider):
    root_directory = Ref.directory(uri='plex:directory', name='Plex Music')

    def __init__(self, *args, **kwargs):
        super(PlexLibraryProvider, self).__init__(*args, **kwargs)
        self.plex = self.backend.plex
        self.library_id = self.backend.library_id
        self.music = self.backend.music
        # TODO try if we can serialize the tree and reuse it safely when getting a new session later
        # TODO maybe serialize the data in another way, to JSON, sqlite or similar instead.
        # TODO try populating the tree with multiple threads, run populate_artist() in multiple threads and sync only adding to the root node
        self.plex_cache = PlexTree(self.plex)
        self._root = []
        self._root.append(Ref.directory(uri='plex:album', name='Albums'))
        self._root.append(Ref.directory(uri='plex:artist', name='Artists'))

    def _item_ref(self, item, item_type):
        if item_type == 'track':
            _ref = Ref.track
        else:
            _ref = Ref.directory
        return _ref(uri=self.backend.plex_uri(item.ratingKey, 'plex:{}'.format(item_type)),
                    name=item.title)

    @MWT(timeout=3600)
    def browse(self, uri):
        logger.debug('browse: %s', str(uri))
        if not uri:
            return []
        if uri == self.root_directory.uri:
            return self._root
        parts = uri.split(':')

        # For now, we only browse the music library in the config.
        # Could filter,flatmap all music sections to browse all music in theory too.
        artist_nodes = self.plex_cache.artists()
        # albums
        if uri == 'plex:album':
            logger.debug('self._browse_albums()')
            albums = list()
            for a in artist_nodes:
                try:
                    # Map the album nodes back into the library item
                    albums += [node.item for node in a.children]
                except Exception as e:
                    logger.warning('Failed to process albums for {}: {}'.format(a, e))
            # logger.info('Albums: {}'.format([a.title for a in albums]))
            logger.debug('{} albums found'.format(len(albums)))
            return [self._item_ref(item, 'album') for item in albums]

        # a single album
        # uri == 'plex:album:album_id'
        if len(parts) == 3 and parts[1] == 'album':
            # TODO use cache
            logger.debug('self._browse_album(uri)')
            album_id = parts[2]
            key = '/library/metadata/{}/children'.format(album_id)
            return [self._item_ref(item, 'track') for item in self.plex.fetchItems(key)]

        # artists
        if uri == 'plex:artist':
            artists = [node.item for node in artist_nodes]
            logger.debug('self._browse_artists()')
            return [self._item_ref(item, 'artist') for item in artists]

        # a single artist
        # uri == 'plex:artist:artist_id'
        if len(parts) == 3 and parts[1] == 'artist':
            # TODO use cache
            logger.debug('self._browse_artist(uri)')
            artist_id = parts[2]
            # get albums and tracks
            ret = []
            for item in self.plex.fetchItems('/library/metadata/{}/children'.format(artist_id)):
                ret.append(self._item_ref(item, 'album'))
            # for item in self.plex.fetchItems('/library/metadata/{}/allLeaves'.format(artist_id)):
            #    ret.append(self._item_ref(item, 'track'))
            return ret

        # all tracks of a single artist
        # uri == 'plex:artist:artist_id:all'
        if len(parts) == 4 and parts[1] == 'artist' and parts[3] == 'all':
            # TODO use cache
            logger.debug('self._browse_artist_all_tracks(uri)')
            artist_id = parts[2]
            return [self._item_ref(item, 'track') for item in
                    self.plex.fetchItems('/library/metadata/{}/allLeaves'.format(artist_id))]

        logger.debug('Unknown uri for browse request: %s', uri)

        return []

    @MWT(timeout=3600)
    def lookup(self, uri):
        '''Lookup the given URIs.
        Return type:
        list of mopidy.models.Track '''

        parts = uri.split(':')

        if uri.startswith('plex:artist:'):
            # get all tracks for artist
            item_id = parts[2]
            plex_uri = '/library/metadata/{}/allLeaves'.format(item_id)
        elif uri.startswith('plex:album:'):
            # get all tracks for album
            item_id = parts[2]
            plex_uri = '/library/metadata/{}/children'.format(item_id)
        elif uri.startswith('plex:track:'):
            # get track
            item_id = parts[2]
            plex_uri = '/library/metadata/{}'.format(item_id)

        ret = []
        for item in self.plex.query(plex_uri):
            plextrack = self.plex.fetchItem(int(item.attrib['ratingKey']))
            ret.append(wrap_track(plextrack, self.backend.plex_uri))
        return ret

    # @MWT(timeout=3600)
    def get_images(self, uris):
        '''Lookup the images for the given URIs

        Backends can use this to return image URIs for any URI they know about be it tracks, albums, playlists... The lookup result is a dictionary mapping the provided URIs to lists of images.

        Unknown URIs or URIs the corresponding backend couldn’t find anything for will simply return an empty list for that URI.

        Parameters: uris (list of string) – list of URIs to find images for
        Return type:    {uri: tuple of mopidy.models.Image}'''
        return None

    #@MWT(timeout=3600)
    def search(self, query=None, uris=None, exact=False):
        '''Search the library for tracks where field contains values.

        Parameters:
        query (dict) – one or more queries to search for - the dict's keys being:
              {
                  'any': *, # this is what we get without explicit modifiers
                  'albumartist': *,
                  'date': *,
                  'track_name': *,
                  'track_number': *,
              }


        uris (list of string or None) – zero or more URI roots to limit the search to
        exact (bool) – if the search should use exact matching

        Returns mopidy.models.SearchResult, which has these properties
            uri (string) – search result URI
            tracks (list of Track elements) – matching tracks
            artists (list of Artist elements) – matching artists
            albums (list of Album elements) – matching albums
        '''

        logger.debug("Searching Plex for track '%s'", query)
        if query is None:
            logger.debug('Ignored search without query')
            return SearchResult(uri='plex:search')

        if 'uri' in query and False:  # TODO add uri limiting
            pass
        else:
            search_query = ' '.join(query.values()[0])

        search_uri = 'plex:search:%s' % urllib.quote(search_query.encode('utf-8'))
        logger.debug("Searching Plex with query '%s'", search_query)

        artists = []
        tracks = []
        albums = []
        result = [node.item for node in self.plex_cache.search(search_query)]
        if len(result) > 1:
            logger.info("Using cached search results for query '%s'", search_query)
            for hit in result:
                if isinstance(hit, plexaudio.Artist):
                    artists.append(wrap_artist(hit, self.backend.plex_uri))
                elif isinstance(hit, plexaudio.Track):
                    tracks.append(wrap_track(hit, self.backend.plex_uri))
                elif isinstance(hit, plexaudio.Album):
                    albums.append(wrap_album(hit, self.backend.plex_uri, self.backend.resolve_uri))
            return SearchResult(
                uri=search_uri,
                tracks=tracks,
                artists=artists,
                albums=albums
            )

        for hit in self.plex.search(search_query):
            if isinstance(hit, plexaudio.Artist):
                artists.append(wrap_artist(hit, self.backend.plex_uri))
            elif isinstance(hit, plexaudio.Track):
                tracks.append(wrap_track(hit, self.backend.plex_uri))
            elif isinstance(hit, plexaudio.Album):
                albums.append(wrap_album(hit, self.backend.plex_uri, self.backend.resolve_uri))

        logger.debug("Got results: %s, %s, %s", artists, tracks, albums)

        return SearchResult(
            uri=search_uri,
            tracks=tracks,
            artists=artists,
            albums=albums
        )


def wrap_track(plextrack, plex_uri_method):
    '''Wrap a plex search result in mopidy.model.track'''
    return Track(uri=plex_uri_method(plextrack.ratingKey, 'plex:track'),
                 name=plextrack.title,
                 artists=[Artist(uri=plex_uri_method(plextrack.grandparentKey, 'plex:artist'),
                                 name=plextrack.grandparentTitle)],
                 album=Album(uri=plex_uri_method(plextrack.parentKey, 'plex:album'),
                             name=plextrack.parentTitle),
                 track_no=None,  # plextrack.index,
                 length=plextrack.duration,
                 # TODO: bitrate=plextrack.media.bitrate,
                 comment=plextrack.summary
                 )


def wrap_artist(plexartist, plex_uri_method):
    '''Wrap a plex search result in mopidy.model.artist'''
    return Artist(uri=plex_uri_method(plexartist.ratingKey, 'plex:artist'),
                  name=plexartist.title)


def wrap_album(plexalbum, plex_uri_method, resolve_uri_method):
    '''Wrap a plex search result in mopidy.model.album'''
    return Album(uri=plex_uri_method(plexalbum.ratingKey, 'plex:album'),
                 name=plexalbum.title,
                 artists=[Artist(uri=plex_uri_method(plexalbum.parentKey, 'plex:artist'),
                                 name=plexalbum.parentTitle)],
                 num_tracks=len(plexalbum.tracks()),
                 num_discs=None,
                 date=str(plexalbum.year),
                 images=[resolve_uri_method(plexalbum.thumb),
                         resolve_uri_method(plexalbum.art)]
                 )


# Data structure to store artist album tracks mapping at startup for quick search and browsing
def populate_artist(artist, artist_node):
    artist_albums = []
    try:
        artist_albums = artist.albums()
    except:
        logger.error("Error parsing albums for artist '%s'", artist.title)

    albums = [PlexTree.Node(item.title, item) for item in artist_albums]
    if len(artist_node.children) == 0:
        artist_node.children = albums
    else:
        [artist_node.children.append(item) for item in albums]
    for album in albums:
        tracks = [PlexTree.Node(item.title, item) for item in album.item.tracks()]
        album.children.append(tracks)


class PlexTree:
    def __init__(self, plex):
        self.plex = plex
        self.root = PlexTree.Node("", None)
        sections = plex.library.sections()
        # We only want to look through music sections
        music_sections = [item for item in sections if item.type == 'artist']
        logger.info("Initializing Plex cache tree...")
        # Initialize the tree
        for section in music_sections:
            logger.info("Caching music section %s", section.title)
            artists = section.searchArtists()
            for artist in artists:
                logger.info("Adding artist '%s'", artist.title)
                # Search for existing artists with the same name for merging
                result = [node for node in self.artists() if node.name == artist.title]
                if not result:
                    # New artist
                    artist_node = self.root.add_new_item(artist)
                    populate_artist(artist, artist_node)
                elif len(result) == 1:
                    logger.info("Appending to existing artist")
                    existing_artist = result[0]
                    # This will add all the albums and tracks of the new artist (same name) to the existing node,
                    # merging the items from different libraries (might change this in the future,
                    # not merging when album exists already, etc.)
                    populate_artist(artist, existing_artist)
                else:
                    logger.error("Multiple results found for artist string %s", artist.title)

    def search(self, search_string):
        return self.root.search(search_string)

    def artists(self):
        return self.root.children

    class Node:
        def __init__(self, name, item):
            self.name = name
            self.item = item
            self.children = []

        def search(self, search_string):
            results = []
            if search_string in self.name.lower():
                results.append(self)
            for item in self.children:
                results.append(item.search(search_string))
            return results

        # Search for items matching the string exactly, for populating the tree initially
        def search_exact(self, search_string):
            results = []
            if search_string == self.name:
                results.append(self)
            for item in self.children:
                if not isinstance(item, PlexTree.Node):
                    print(dir(item))
                    print(item)
                [results.append(item) for item in item.search_exact(search_string)]
            return results

        def add_new_item(self, item):
            if item.type == 'artist':
                node = PlexTree.Node(item.title, item)
                self.children.append(node)
                return node
            if item.type == 'album':
                album_artist = item.artist().title
                result = self.search(album_artist)
                if len(result) > 1:
                    logger.error("More than one existing artist for key %s", album_artist)
                elif len(result) == 1:
                    if result[0].item.type == 'artist':
                        result[0].children.append(item)
                else:
                    logger.error("No artist '%s' found for album '%s'", album_artist, item.title)
            if item.type == 'track':
                logger.error("Track items will not be added directly to the tree as of now, bad time complexity")
