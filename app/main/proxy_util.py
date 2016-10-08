from urllib.parse import urlparse
import csv
import asyncio
import os
import re
from freeproxy import from_hide_my_ip, from_cyber_syndrome, from_free_proxy_list, from_xici_daili
import requests
from proxybroker import Broker
from random import randrange
import geoip
import socket
# TODO instead of  proxyfile use db table for active proxies
# from .. import db

# For lcoal testing please override the path to the proxy list with the actual one. eg.:
# proxy_util.proxy_path = os.path.abspath(os.path.expanduser("~/") + "PycharmProjects/STW/static/")
proxy_path = os.path.abspath(os.path.expanduser("~/") + "StampTheWeb/static/")
# regular expression to check URL, see https://mathiasbynens.be/demo/url-regex
url_specification = re.compile('^(https?|ftp)://[^\s/$.?#].[^\s]*$')
base_path = 'app/pdf/'
default_event_loop = None


"""def get_proxy_location(ip_address):
    ""
    Looks up the location of an IP Address and returns the two-letter ISO country code.

    :author: Sebastian
    :param ip_address: The IP Address to get the location for.
    :return: The country_code as two letter string
    ""
    # Automatically geolocate the connecting IP
    print("Getting the proxy location of:{}".format(str(ip_address)))
    url = 'http://freegeoip.net/json/' + ip_address
    with closing(urlopen(url)) as response:
        location = json.loads(str(response.read().decode()))
        return location['country_code']
"""


def get_rand_proxy(proxy_list=None, level=0):
    """
    Retrieve one random proxy from the proxy list. Recursively fetches a random, working proxy to return.

    :author: Sebastian
    :return: One randomly chosen proxy
    """
    if level > 16:
        return None
    print("Getting a random, active proxy {}.".format(level))
    proxies = proxy_list or get_proxy_list()
    proxy = proxies[randrange(0, len(proxies))]
    if is_proxy_alive(proxy[1], 3):
        return proxy
    else:
        proxies.remove(proxy)
        return get_rand_proxy(proxies, level=level+1)


def get_proxy_list(update=False, prox_loc=None):
    """
    Get a list of available proxies to use from the proxy list.
    # TODO check the proxy status.

    :author: Sebastian
    :param prox_loc: Defaults to None. If specified only proxies from this location are taken into account.
    :param update: Is set to False by default. If set to True the proxy list will be fetched again.
    This takes quite a while!
    :return: A list of lists with 3 values representing proxies [1] with their location [0].
    """
    print("Getting the proxylist")
    proxy_list = []
    if update:
        proxy_list = update_proxies(prox_loc)
    else:
        with open(proxy_path + "/proxy_list.tsv", "rt", encoding="utf8") as tsv:
            for line in csv.reader(tsv, delimiter="\t"):
                if prox_loc is None or prox_loc == line[0]:
                    proxy_list.append([line[0], line[1], None])

    print("Returning the proxy list")
    return proxy_list


def update_proxies(prox_loc=None):
    """
    Checks the proxies stored in the proxy_list.tsv file. If there are proxies that are inactive,
    new proxies from that country are gathered and stored in the file instead.

    :author: Sebastian
    :param prox_loc: A new location to be added to the countries already in use. Defaults to None.
    :return: A list of active proxies.
    """
    print("Start updating the proxy list")
    country_list = []
    with open(proxy_path + "/proxy_list.tsv", "r", encoding="utf8") as tsv:
        for line in csv.reader(tsv, delimiter="\t"):
            country_list.append(line[0])
        if prox_loc:
            country_list.append(prox_loc)
        country_list = set(country_list)
    print(country_list)
    print("Getting the proxies now. That may take quite a while!")
    try:
        proxy_list = gather_proxies(country_list)
    except RuntimeError as e:
        print(str(e))
        asyncio.new_event_loop()
        proxy_list = gather_proxies(country_list)

        # Does not take country list into account - Fallback not needed anymore until next error in proxybroker package
        #proxy_list = gather_proxies_alternative()
    print("All proxies gathered!")

    with open(proxy_path + "/proxy_list.tsv", "w", encoding="utf8") as tsv:
        # tsv.writelines([proxy[0] + "\t" + proxy[1] for proxy in proxy_list])
        for proxy in proxy_list:
            tsv.write("{}\t{}\n".format(proxy[0], proxy[1]))
            print("writing proxy {} from {} to file.".format(proxy[1], proxy[0]))
    print("All {} proxies wrote to file!".format(len(proxy_list)))
    return proxy_list


def gather_proxies(countries):
    """
    This method uses the proxybroker package to asynchronously get two new proxies per specified country
    and returns the proxies as a list of country and proxy.

    :author: Sebastian
    :param countries: The ISO style country codes to fetch proxies for. Countries is a list of two letter strings.
    :return: A list of proxies that are themselves a list with  two paramters[Location, proxy address].
    """
    # TODO !! May take more than 45 minutes !! Run in separate thread?
    proxy_list = []
    types = ['HTTP']
    for country in countries:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            print("----New event loop")
            loop = asyncio.new_event_loop()

        proxies = asyncio.Queue(loop=loop)
        broker = Broker(proxies, loop=loop)

        loop.run_until_complete(broker.find(limit=2, countries=country, types=types))

        while True:
            proxy = proxies.get_nowait()
            if proxy is None:
                break
            print(str(proxy))
            proxy_list.append([country, "{}:{}".format(proxy.host, str(proxy.port))])
    return proxy_list


def get_one_proxy(country, types='HTTP'):
    """
    Find one new, working proxy from the specified country. Run time of this method depends heavily on the country
    specified as for some countries it is hard to find proxies (e.g. Myanmar).

    :author: Sebastian
    :param country: Two-letter ISO formatted country code. If a lookup is needed before calling this method, please
    consult /static/country_codes.csv.
    :param types: The type of proxy to search for as a list of strings. Defaults to HTTP.
    If only one type should be specified a string like "HTTPS" will also work.
    Other possibilities are HTTPS, SOCKS4, SOCKS5. E.g. types=['HTTP, HTTPS']
    :return: A string containing the newly found proxy from the specified country in <Proxy IP>:<Port> notation.
    """
    print("Fetching one proxy from: {}".format(country))
    try:
        if type(types) is not list:
            types = [types]
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
            loop = asyncio.get_event_loop()

        proxies = asyncio.Queue(loop=loop)
        broker = Broker(proxies, loop=loop)
        print(type(country))
        print(type(types))
        loop.run_until_complete(broker.find(limit=1, countries=[country], types=types))

        while True:
            proxy = proxies.get_nowait()
            if proxy is None:
                break
            print("Proxy from {} is: {}:{}".format(country, proxy.host, str(proxy.port)))

            return "{}:{}".format(proxy.host, str(proxy.port))
        return None
    except RuntimeError as e:
        print("Proxybroker not working properly due to {}\n, trying the static proxylist.".format(str(e)))
        return get_one_proxy_alternative(country)


def get_one_proxy_alternative(country):
    """
    Fetches one active proxy from the specified country from the proxy list.
    :param country:
    :return:
    """
    proxies = get_proxy_list()
    for proxy in proxies:
        if country == proxy[0] and is_proxy_alive(proxy[1]):
            return proxy
    return None


def gather_proxies_alternative():
    """
    Alternative to gather_proxies that uses freeproxy to gather proxies from different sources.
    It usually yields more than # # proxies. It only returns active proxies with the country code added to them.

    :return: A List of Lists. Each inner list has three values: Index 0 is the two-letter ISO country code of the proxy,
    Index 1 is the proxy with port number and index 2 is None in the beginning.
    """
    proxies = list(set(from_xici_daili() + from_cyber_syndrome() + from_hide_my_ip() + from_free_proxy_list()))
    print(proxies)
    print("{} different proxies gathered".format(str(len(proxies))))
    proxies = test_proxies(proxies)
    #proxies = t_prox(proxies, timeout=5, single_url="http://baidu.com")
    print("{} working proxies gathered".format(str(len(proxies))))

    proxy_list = list()
    countries = set()
    for proxy in proxies:
        split_proxy = proxy.split(":")
        country = ip_lookup_country(split_proxy[0])
        countries.add(country)
        proxy_list.append([country, "{}:{}".format(split_proxy[0], split_proxy[1])])
    print(str(len(countries)))
    print(countries)
    #proxy_uri_list = freeproxy.fetch_proxies()
    #print(proxy_uri_list)
    return proxy_list


def test_proxies(proxies, timeout=4):
    """
    Tests a list of proxies and returns only the alive ones.
    Timeout is set to timeout seconds so some working proxies that respond slowly will also be removed.
    Due to the timeout of per default four seconds this method might take a long while to finish if many proxies
    need checking.
    #TODO Proxy gathering usually takes less than two minutes but the testing takes above an hour for all proxies.

    :author: Sebastian
    :param proxies: List of proxies that this method checks the status for.
    :param timeout: The timeout to use to check each proxy. Defaults to 4.
    :return: A list of proxies responding within timeout seconds.
    """
    # TODO could be implemented to use multithreading in order to increase speed for many proxies
    print("Testing {} proxies".format(str(len(proxies))))
    tested_proxies = list()
    for proxy in set(proxies):
        if is_proxy_alive(proxy, timeout):
            tested_proxies.append(proxy)
    return tested_proxies


def is_proxy_alive(proxy, timeout=8):
    """
    Tests whether the specified HTTP proxy is alive. Therefore two websites are trying to be accessed "google.com",
    and "baidu.com". If either one is working the proxy is considered alive.

    :param proxy: The proxy to check. String in <Host>:<Post> notation.
    :param timeout: The timeout within which a response should be retrieved via the proxy. Defaults to 8 seconds.
    :return: Either True if the proxy is alive ot False if it is not alive.
    """
    try:
        res = requests.head("http://google.com", timeout=timeout, proxies={"http": "http://" + proxy},
                            allow_redirects=True)
        if res.status_code <= 400:
            print("Proxy {} is alive!".format(proxy))
            return True
    except IOError as e:
        print(str(e))

    try:
        res = requests.head("http://baidu.com/", timeout=timeout, proxies={"http": "http://" + proxy},
                            allow_redirects=True)
        if res.status_code <= 400:
            print("Proxy {} is alive!".format(proxy))
            return True
    except IOError as e:
        print(str(e))
    return False


def get_country_of_url(url):
    """
    Takes a URL and computes the country where this website is hosted to return.

    :author: Sebastian
    :param url: The url of the website to get the country of.
    :return: The country as two letter ISO-code of the website specified by the url.
    """
    return ip_lookup_country(_lookup_website_ip(url))


def ip_lookup_country(ip):
    """
    Looks up an IP address in the MaxMindDataBase GeoLite2-Country.mmdb to find out to which country the IP address l
    links to.
    This DB should be updated once in a while.
    (For update purposes Database downloadable from: http://dev.maxmind.com/geoip/geoip2/geolite2/

    :author: Sebastian
    :param ip: The IP address as string (-- without the port --).
    :raises ValueError: A Value Error is raised if the IP address specified does not match IP specifications.
    :return: The location of the IP address as two letter ISO-code.
    """
    database = geoip.open_database("/home/sebastian/PycharmProjects/STW/static/GeoLite2-Country.mmdb")
    return database.lookup(ip).country


def _lookup_website_ip(url):
    """
    Looks up a URL to find out which IP address it is linked to.

    :author: Sebastian
    :param url: The URL to get the IP address for.
    :return: Returns the IP address of the website.
    """
    domain = urlparse(url).netloc

    return socket.gethostbyname_ex(domain)[2][0]
