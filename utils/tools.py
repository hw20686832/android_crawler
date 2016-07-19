# coding:utf-8
import humanize
import re

def intkilo(num):
    i = int(num)
    if i >= 10000:
        return "%sk+" % humanize.intcomma(i/1000)

    return humanize.intcomma(i)

def remove_downloads(from_num_string):
    # remove Downloads and downloads
    to_num_string = from_num_string
    download_index = from_num_string.find('ownlo')
    if download_index >= 0:
        try:
            to_num_string = from_num_string[:download_index - 1].strip()
        except:
            pass
    return to_num_string

def strCount_to_intCount(from_num_string):
    """
    Remove ',', '+' transfom k/m/b to 000/000000/000000000
    E.g. 100,000+ to 100000
    100k+ to 100000
    :param from_num_string:
    :return: to_num_string
    """
    try:
        to_num_string = from_num_string.strip()
        to_num_string = to_num_string.lower().replace(',', '').replace('+', '')
        if 'k' in to_num_string:
            to_num_string = to_num_string.replace('k', '000')
        elif 'm' in to_num_string:
            to_num_string = to_num_string.replace('m', '000000')
        elif 'b' in to_num_string:
            to_num_string = to_num_string.replace('b', '000000000')
        to_num_string = int(to_num_string)
    except:
        to_num_string = int(re.search('.*?(\d+).*?', from_num_string.replace(',', '')).group(1) or 0)

    return to_num_string

