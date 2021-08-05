'''
WikiTeams.pl scientific dataset creator
Calculating attributes x for developers
at one static moment on time (now)
If you are interested in dymanic data, please visit
https://github.com/wikiteams/github-data-tools/tree/master/pandas

@since 1.4.0408
@author Oskar Jarczyk

@update 18.06.2014
'''

version_name = 'Version 2.2 codename: JJ'

from intelliRepository import MyRepository
from github import Github, UnknownObjectException, GithubException
import csv
from Queue import Queue
import getopt
import scream
import gc
import os
import os.path
import sys
import codecs
import cStringIO
from bs4 import BeautifulSoup
from lxml import html, etree
import urllib2
from pyvirtualdisplay import Display
from selenium import webdriver
import __builtin__
import socket
import time
import threading


count___ = 'selenium'

auth_with_tokens = True
use_utf8 = True

resume_on_repo = None
resume_on_repo_inclusive = True
reverse_queue = False

resume_stage = None
resume_entity = None

no_of_threads = 20
intelli_no_of_threads = False

github_clients = list()
github_clients_ids = list()

safe_margin = 100
timeout = 50
sleepy_head_time = 25


def is_number(s):
    try:
        float(s)  # for int, long and float
    except ValueError:
        try:
            complex(s)  # for complex
        except ValueError:
            return False
    return True


def analyze_tag(tag):
    number = filter(lambda x: x.isdigit(), str(tag))
    return number


def usage():
    f = open('usage.txt', 'r')
    for line in f:
        print line


try:
    opts, args = getopt.getopt(sys.argv[1:], "ht:u:r:s:e:vx:z:qim:j:", ["help", "tokens=",
                               "utf8=", "resume=", "resumestage=", "entity=", "verbose",
                               "threads=", "timeout=", "reverse", "intelli", "safemargin=", "sleep="])
except getopt.GetoptError as err:
    # print help information and exit:
    print str(err)  # will print something like "option -a not recognized"
    usage()
    sys.exit(2)

for o, a in opts:
    if o in ("-v", "--verbose"):
        __builtin__.verbose = True
        scream.ssay('Enabling verbose mode.')
    elif o in ("-h", "--help"):
        usage()
        sys.exit()
    elif o in ("-t", "--tokens"):
        auth_with_tokens = (a in ['true', 'True'])
    elif o in ("-u", "--utf8"):
        use_utf8 = (a not in ['false', 'False'])
    elif o in ("-r", "--resume"):  # if running after a long pause, consider starting from new
        resume_on_repo = a  # remember dataset is a static one point in time
        scream.ssay('Resume on repo? ' + str(resume_on_repo))
    elif o in ('--resumeinclusive'):
        resume_on_repo_inclusive = True
        scream.ssay('Resume on repo with inclusion')
    elif o in ("-s", "--resumestage"):
        resume_stage = a
        scream.ssay('Resume on repo with stage ' + str(resume_stage))
    elif o in ("-x", "--threads"):
        no_of_threads = a
        scream.ssay('Number of threads to engage ' + str(no_of_threads))
    elif o in ("-z", "--timeout"):
        timeout = int(float(a))
        scream.ssay('Connection timeout ' + str(timeout))
    elif o in ("-m", "--safemargin"):
        safemargin = int(float(a))
        scream.ssay('Connection timeout ' + str(timeout))
    elif o in ("-j", "--sleep"):
        sleepy_head_time = int(float(a))
        scream.ssay('Retry time: ' + str(sleepy_head_time))
    elif o in ("-i", "--intelli"):
        intelli_no_of_threads = True
        scream.ssay('Matching thread numbers to credential? ' + str(intelli_no_of_threads))
    elif o in ("-e", "--entity"):
        resume_entity = a
        scream.ssay('Resume on stage with entity ' + str(resume_entity))
    elif o in ("-q", "--reverse"):
        reverse_queue = (a not in ['false', 'False'])
        scream.ssay('Queue will be reversed, program will start from end ' + str(reverse_queue))

repos = Queue()

'''
Explanation of an input data, theye are CSV file with data
retrieved from Google BigQuery consisted of repo name, owner
and sorted by number of forks and watchers, for analysis we
take around 32k biggest GitHub repositories
'''
input_filename = 'result_stargazers_2013_final_mature.csv'
repos_reported_nonexist = open('reported_nonexist_fifo.csv', 'ab', 0)
repos_reported_execution_error = open('reported_execution_error_fifo.csv', 'ab', 0)


class Stack:
    def __init__(self):
        self.__storage = []

    def isEmpty(self):
        return len(self.__storage) == 0

    def push(self, p):
        self.__storage.append(p)

    def pop(self):
        return self.__storage.pop()


class WriterDialect(csv.Dialect):
    strict = True
    skipinitialspace = True
    quoting = csv.QUOTE_MINIMAL
    delimiter = ','
    escapechar = '\\'
    quotechar = '"'
    lineterminator = '\n'


class RepoReaderDialect(csv.Dialect):
    strict = True
    skipinitialspace = True
    quoting = csv.QUOTE_ALL
    delimiter = ';'
    escapechar = '\\'
    quotechar = '"'
    lineterminator = '\n'


class UTF8Recoder:
    """
    Iterator that reads an encoded stream and re-encodes the input to UTF-8
    """
    def __init__(self, f, encoding):
        self.reader = codecs.getreader(encoding)(f)

    def __iter__(self):
        return self

    def next(self):
        return self.reader.next().encode("utf-8")


class UnicodeReader:
    """
    A CSV reader which will iterate over lines in the CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=csv.excel, encoding="utf-8", **kwds):
        f = UTF8Recoder(f, encoding)
        self.reader = csv.reader(f, dialect=dialect, **kwds)

    def next(self):
        row = self.reader.next()
        return [unicode(s, "utf-8") for s in row]

    def __iter__(self):
        return self


class UnicodeWriter:
    """
    A CSV writer which will write rows to CSV file "f",
    which is encoded in the given encoding.
    """

    def __init__(self, f, dialect=WriterDialect, encoding="utf-8", **kwds):
        # Redirect output to a queue
        self.queue = cStringIO.StringIO()
        self.writer = csv.writer(self.queue, dialect=dialect, **kwds)
        self.stream = f
        self.encoder = codecs.getincrementalencoder(encoding)()

    def writerow(self, row):
        self.writer.writerow([s.encode("utf-8") for s in row])
        # Fetch UTF-8 output from the queue ...
        data = self.queue.getvalue()
        data = data.decode("utf-8")
        # ... and reencode it into the target encoding
        data = self.encoder.encode(data)
        # write to the target stream
        self.stream.write(data)
        # empty queue
        self.queue.truncate(0)

    def writerows(self, rows):
        for row in rows:
            self.writerow(row)

'''
developer_revealed(repository, repo, contributor, result_writer)
return nothing, but writes final result row to a csv file
repository = github object, repo = my class object, contributor = nameduser
'''
def developer_revealed(thread_getter_instance, repository, repo, contributor, result_writer):
    developer_login = contributor.login
    scream.say('Assigning a contributor: ' + str(developer_login) + ' to a repo: ' + str(repository.name))
    developer_name = contributor.name
    # 1 Ilosc osob, ktore dany deweloper followuje [FollowEvent]
    developer_followers = contributor.followers
    # 2 Ilosc osob, ktore followuja dewelopera [FollowEvent]
    developer_following = contributor.following

    developer_location = contributor.location
    developer_total_private_repos = contributor.total_private_repos
    developer_total_public_repos = contributor.public_repos

    # 5.  Ilosc repo, ktorych nie tworzyl, w ktorych jest team member [TeamAddEvent] [MemberEvent]
    developer_collaborators = contributor.collaborators
    # 6.  Ilosc repo, ktorych nie tworzyl, w ktorych jest contributorem [PushEvent] [IssuesEvent] [PullRequestEvent] [GollumEvent]
    developer_contributions = contributor.contributions

    # - Ilosc projektow przez niego utworzonych
    his_repositories = contributor.get_repos()

    while True:
        total_his_repositories = 0
        total_his_stars = 0
        total_his_watchers = 0
        total_his_forks = 0
        total_his_has_issues = 0
        total_his_has_wiki = 0
        total_his_open_issues = 0
        total_network_count = 0
        total_his_collaborators = 0
        total_his_contributors = 0

        if count___ == 'selenium':
            total_his_commits = 0
            total_his_branches = 0
            total_his_releases = 0
            total_his_issues = 0
            total_his_pull_requests = 0

        try:
            for his_repo in his_repositories:
                total_his_repositories += 1
                total_his_forks += his_repo.forks_count
                total_his_stars += his_repo.stargazers_count
                total_his_watchers += his_repo.watchers_count
                total_his_has_issues += 1 if his_repo.has_issues else 0
                total_his_has_wiki += 1 if his_repo.has_wiki else 0
                total_his_open_issues += his_repo.open_issues
                total_network_count += his_repo.network_count

                if count___ == 'api':

                    # 3 Ilosc deweloperow, ktorzy sa w projektach przez niego utworzonych [PushEvent] [IssuesEvent] [PullRequestEvent] [GollumEvent]
                    total_his_contributors = None
                    while True:
                        try:
                            total_his_contributors = 0
                            #total_his_contributors = his_repo.get_contributors().totalCount -- this is buggy and will make errors
                            total_his_contributors += sum(1 for temp_object in his_repo.get_contributors())
                            break
                        except:
                            freeze('Exception in getting total_his_contributors')
                    assert total_his_contributors is not None

                    # 4 Ilosc kontrybutorow, ktorzy sa w projektach przez niego utworzonych
                    total_his_collaborators = None
                    while True:
                        try:
                            total_his_collaborators = 0
                            #total_his_collaborators = his_repo.get_collaborators().totalCount -- this is buggy and will make errors
                            total_his_collaborators += sum(1 for temp_object in his_repo.get_collaborators())
                            break
                        except:
                            freeze('Exception in getting total_his_collaborators')
                    assert total_his_collaborators is not None
                elif count___ == 'selenium':
                    scream.say('Using selenium for thread about  ' + developer_login + ' repositories')
                    result = thread_getter_instance.analyze_with_selenium(his_repo)  # wyciagnij statystyki przez selenium, i zwroc w tablicy:
                    # commity, branche, releases, contributors, issues, pull requests
                    if result['status'] == '404':
                        continue
                    total_his_commits += result['commits']
                    total_his_branches += result['branches']
                    total_his_releases += result['releases']
                    total_his_issues += result['issues']
                    total_his_pull_requests += result['pulls']
                    total_his_contributors += result['contributors']
                else:
                    while True:
                        try:
                            his_contributors = set()
                            stats = his_repo.get_stats_contributors()
                            assert stats is not None
                            for stat in stats:
                                if str(stat.author.login).strip() in ['None', '']:
                                    continue
                                his_contributors.add(stat.author.login)
                            total_his_contributors += len(his_contributors)
                            break
                        except Exception as exc:
                            scream.log_warning('Not ready data while revealing details.. ' +
                                               ', error({0})'.format(str(exc)), True)
                            freeze('StatsContribution not ready.. waiting for the server to provide good data')
            break
        except Exception as e:
            freeze(str(e) + ' in main loop of developer_revealed()')
            his_repositories = contributor.get_repos()

    # Firma developera
    company = contributor.company
    created_at = contributor.created_at
    # Czy developer chce byc zatrudniony
    hireable = contributor.hireable

    if not use_utf8:
        result_writer.writerow([str(repo.getUrl()), str(repo.getName()), str(repo.getOwner()),
                               str(repo.getStargazersCount()), str(repo.getWatchersCount()), str(developer_login),
                               (str(developer_name) if developer_name is not None else ''), str(developer_followers), str(developer_following),
                               str(developer_collaborators), (str(company) if company is not None else ''), str(developer_contributions),
                               str(created_at), (str(hireable) if hireable is not None else ''),
                               str(total_his_repositories), str(total_his_stars), str(total_his_collaborators), str(total_his_contributors),
                               str(total_his_watchers), str(total_his_forks), str(total_his_has_issues),
                               str(total_his_has_wiki), str(total_his_open_issues), str(total_network_count),
                               str(developer_location), str(developer_total_private_repos), str(developer_total_public_repos),
                               str(total_his_issues), str(total_his_pull_requests)])
    else:
        result_writer.writerow([repo.getUrl(), repo.getName(), repo.getOwner(), str(repo.getStargazersCount()), str(repo.getWatchersCount()), developer_login,
                               (developer_name if developer_name is not None else ''), str(developer_followers), str(developer_following),
                               str(developer_collaborators), (company if company is not None else ''), str(developer_contributions),
                               str(created_at), (str(hireable) if hireable is not None else ''),
                               str(total_his_repositories), str(total_his_stars), str(total_his_collaborators), str(total_his_contributors),
                               str(total_his_watchers), str(total_his_forks), str(total_his_has_issues),
                               str(total_his_has_wiki), str(total_his_open_issues), str(total_network_count),
                               developer_location, str(developer_total_private_repos), str(developer_total_public_repos),
                               str(total_his_issues), str(total_his_pull_requests)])


def freeze(message):
    global sleepy_head_time
    scream.say('Sleeping for ' + str(sleepy_head_time) + ' seconds. Reason: ' + str(message))
    time.sleep(sleepy_head_time)


def make_headers(filename_for_headers):
    with open(filename_for_headers, 'ab') as output_csvfile:
        devs_head_writer = UnicodeWriter(output_csvfile) if use_utf8 else csv.writer(output_csvfile, dialect=WriterDialect)
        tempv = ('repo_url', 'repo_name', 'repo_owner', 'stargazers_count', 'watchers_count', 'developer_login', 'developer_name',
                 'developer_followers', 'developer_following', 'developer_collaborators', 'developer_company', 'developer_contributions',
                 'created_at', 'developer_is_hireable', 'total_his_repositories', 'total_in-his-repos_stars',
                 'total_in-his-repos_collaborators', 'total_in-his-repos_contributors',
                 'total_in-his-repos_watchers', 'total_in-his-repos_forks', 'total_in-his-repos_has_issues',
                 'total_in-his-repos_has_wiki', 'total_in-his-repos_open_issues', 'total_network_count',
                 'developer_location', 'developer_total_private_repos',
                 'developer_total_public_repos', 'total_in-his-repos_issues', 'total_in-his-repos_pull_requests')
        devs_head_writer.writerow(tempv)


'''
def build_list_of_programmers(result_set_programmers,
                              repo_key, repository)
returns dict (github user name -> User object) 1..1
key is a string contributor username (login)
second object is actuall PyGithub User instance, meow !
'''
def build_list_of_programmers(result_set_programmers, repo_key, repository):
    result_set = None
    contributors__ = result_set_programmers

    while True:
        result_set = dict()
        try:
            for contributor in contributors__:
                result_set[contributor.login] = contributor
            break
        except TypeError as e:
            scream.log_error('Repo + Contributor TypeError, or paginated through' +
                             ' contributors gave error. ' + key + ', error({0})'.
                             format(str(e)), True)
            repos_reported_execution_error.write(key + os.linesep)
            break
        except socket.timeout as e:
            scream.log_error('Timeout while revealing details.. ' +
                             ', error({0})'.format(str(e)), True)
        except Exception as e:
            scream.log_error('Exception while revealing details.. ' +
                             ', error({0})'.format(str(e)), True)
    return result_set


class GeneralGetter(threading.Thread):
    finished = False
    repository = None
    repo = None
    result_writer = None
    github_client = None
    display = None
    browser = None

    def __init__(self, threadId, repository, repo, result_writer, github_client):
        scream.say('Initiating GeneralGetter, running __init__ procedure.')
        self.threadId = threadId
        threading.Thread.__init__(self)
        self.daemon = True
        self.finished = False
        self.repository = repository
        self.repo = repo
        self.result_writer = result_writer
        self.github_client = github_client

    def run(self):
        scream.cout('GeneralGetter starts work...')
        self.finished = False
        # it is quite reasonable to initiate a display driver for selenium
        # per one getter, threads work on jobs linear so its the max partition of driver
        # we can allow, multiple threads working on one virtual display - its without sense
        self.initiate_selenium()
        # now its ok to start retrieving data.. allonsy !
        self.get_data()

    def initiate_selenium(self):
        scream.say('Initiating selenium...')
        self.display = Display(visible=0, size=(800, 600))
        self.display.start()
        self.browser = webdriver.Firefox()
        self.browser.implicitly_wait(15)
        scream.say('Selenium ready for action')

    def analyze_with_selenium(self, repository):
        result = dict()
        scream.say('Starting webinterpret..')
        assert repository is not None
        url = repository.html_url
        assert url is not None
        try:
            while True:
                self.browser.set_page_load_timeout(15)
                self.browser.get(url)
                scream.say('Data from web retrieved')
                doc = html.document_fromstring(unicode(self.browser.page_source))
                print url
                scream.say('Continue to work on ' + url)
                scream.say('Page source sent further')

                scream.say('Verify if 404 (repo deleted) otherwise keep on going')
                parallax = doc.xpath('//div[@id="parallax_illustration"]')

                if (len(parallax) > 0):
                    scream.say('Verified that 404 (repo deleted)')
                    result['status'] = '404'
                    return result

                scream.say('Verified that not 404')

                ns = doc.xpath('//ul[@class="numbers-summary"]')
                sunken = doc.xpath('//ul[@class="sunken-menu-group"]')

                scream.say('XPath made some search for ' + url + ' .. move on to bsoup..')
                scream.say('Xpath done searching')
                scream.say('Element found?: ' + str(len(ns) == 1))

                element = ns[0]
                element_sunken = sunken[0]
                local_soup = BeautifulSoup(etree.tostring(element))
                local_soup_sunken = BeautifulSoup(etree.tostring(element_sunken))

                enumarables = local_soup.findAll("li")
                enumarables_more = local_soup_sunken.findAll("li")

                commits = enumarables[0]
                scream.say('enumarables[0]')
                commits_number = analyze_tag(commits.find("span", {"class": "num"}))
                scream.say('analyze_tag finished execution for commits_number')
                result['commits'] = commits_number
                scream.say('enumarables[1]')
                branches = enumarables[1]
                branches_number = analyze_tag(branches.find("span", {"class": "num"}))
                result['branches'] = branches_number
                scream.say('enumarables[2]')
                releases = enumarables[2]
                releases_number = analyze_tag(releases.find("span", {"class": "num"}))
                result['releases'] = releases_number
                scream.say('enumarables[3]')
                contributors = enumarables[3]
                contributors_number = analyze_tag(contributors.find("span", {"class": "num"}))
                result['contributors'] = contributors_number

                if (len(enumarables_more) < 3):
                    scream.say('Issues disabled for this repo')
                    scream.say('enumarables_more[1] (pulls)')
                    pulls_tag = enumarables_more[1]
                    pulls_number = analyze_tag(pulls_tag.find("span", {"class": "counter"}))
                    result['pulls'] = pulls_number
                else:
                    scream.say('enumarables_more[1] (issues)')
                    issues_tag = enumarables_more[1]
                    issues_number = analyze_tag(issues_tag.find("span", {"class": "counter"}))
                    result['issues'] = issues_number
                    scream.say('enumarables_more[2] (pulls)')
                    pulls_tag = enumarables_more[2]
                    pulls_number = analyze_tag(pulls_tag.find("span", {"class": "counter"}))
                    result['pulls'] = pulls_number
                
                result['status'] = 'OK'
                break
        except TypeError as ot:
            scream.say(str(ot))
            scream.say('Scrambled results (TypeError). Maybe GitHub down. Retry')
            time.sleep(5.0)
        except Exception as e:
            scream.say(str(e))
            scream.say('No response from selenium. Retry')
            time.sleep(2.0)
        return result


    def is_finished(self):
        return self.finished if self.finished is not None else False

    def set_finished(self, finished):
        scream.say('Marking the thread ' + str(self.threadId) + ' as finished..')
        self.finished = finished

    def get_data(self):
        global resume_stage

        scream.say('Executing inside-thread method get_data() for: ' + str(self.threadId))
        if resume_stage in [None, 'contributors']:
            #try:
            scream.ssay('Checking size of a ' + str(repo.getKey()) + ' team')
            '1. Team size of a repository'
            contributors = repository.get_contributors()
            assert contributors is not None

            repo_contributors = list()

            contributors_static = build_list_of_programmers(contributors, repo.getKey(), repository)
            for contributor in contributors_static.items():
                while True:
                    try:
                        contributor___ = contributor[1]
                        repo_contributors.append(contributor___)
                        developer_revealed(self, repository, repo, contributor___, result_writer)
                        break
                    except TypeError as e:
                        scream.log_error('Repo + Contributor TypeError, or paginated through' +
                                         ' contributors gave error. ' + key + ', error({0})'.
                                         format(str(e)), True)
                        repos_reported_execution_error.write(key + os.linesep)
                        break
                    except socket.timeout as e:
                        scream.log_error('Timeout while revealing details.. ' +
                                         ', error({0})'.format(str(e)), True)
                        freeze('socket.timeout in paginate through x contributors')
                    except Exception as e:
                        scream.log_error('Exception while revealing details.. ' +
                                         ', error({0})'.format(str(e)), True)
                        freeze(str(e) + ' in paginate through x contributors')

            assert repo_contributors is not None
            repo.setContributors(repo_contributors)
            repo.setContributorsCount(len(repo_contributors))
            scream.log('Added contributors of count: ' + str(len(repo_contributors)) + ' to a repo ' + key)

        scream.say('Marking thread on ' + repo.getKey() + ' as finished..')
        self.finished = True
        scream.say('Terminating thread on ' + repo.getKey() + ' ...')
        self.terminate()


def all_finished(threads):
    are_finished = True
    for thread in threads:
        if not thread.is_finished():
            return False
    return are_finished


def num_working(threads):
    are_working = 0
    for thread in threads:
        if not thread.is_finished():
            are_working += 1
    return are_working


def num_modulo(thread_id_count__):
    global no_of_threads
    return thread_id_count__ % no_of_threads


if __name__ == "__main__":
    '''
    Starts process of work on CSV files which are output of Google Bigquery
    whenever intelliGit.py is executed as an standalone program
    the program reads through the input and gets all data bout programmers
    '''
    scream.say('Start main execution')
    scream.say('Welcome to WikiTeams.pl GitHub repo analyzer!')
    scream.say(version_name)

    secrets = []

    credential_list = []
    # reading the secrets, the Github factory objects will be created in next paragraph
    with open('pass.txt', 'r') as passfile:
        line__id = 0
        for line in passfile:
            line__id += 1
            secrets.append(line)
            if line__id % 4 == 0:
                login_or_token__ = str(secrets[0]).strip()
                pass_string = str(secrets[1]).strip()
                client_id__ = str(secrets[2]).strip()
                client_secret__ = str(secrets[3]).strip()
                credential_list.append({'login': login_or_token__, 'pass': pass_string, 'client_id': client_id__, 'client_secret': client_secret__})
                del secrets[:]

    scream.say(str(len(credential_list)) + ' full credentials successfully loaded')

    # with the credential_list list we create a list of Github objects, github_clients holds ready Github objects
    for credential in credential_list:
        if auth_with_tokens:
            local_gh = Github(login_or_token=credential['pass'], client_id=credential['client_id'],
                              client_secret=credential['client_secret'], user_agent=credential['login'],
                              timeout=timeout)
            github_clients.append(local_gh)
            github_clients_ids.append(credential['login'])
            #scream.say(local_gh.get_api_status)
            scream.say(local_gh.rate_limiting)
        else:
            local_gh = Github(credential['login'], credential['pass'])
            github_clients.append(local_gh)
            scream.say(local_gh.rate_limiting)

    scream.cout('How many Github objects in github_clients: ' + str(len(github_clients)))
    scream.cout('Assigning current github client to the first object in a list')

    github_client = github_clients[0]
    lapis = local_gh.get_api_status()
    scream.say('Current status of GitHub API...: ' + lapis.status + ' (last update: ' + str(lapis.last_updated) + ')')

    if intelli_no_of_threads:
        scream.say('Adjusting no of threads to: ' + str(len(github_clients)))
        no_of_threads = len(github_clients)
        scream.say('No of threads is currently: ' + str(no_of_threads))

    is_gc_turned_on = 'turned on' if str(gc.isenabled()) else 'turned off'
    scream.ssay('Garbage collector is ' + is_gc_turned_on)

    scream.say('WORKING WITH INPUT FILE : ' + input_filename)  # simply 'result_stargazers_2013_final_mature.csv'
    scream.say('This can take a while, max aprox. 2 minutes...')
    filename_ = 'data/' if sys.platform == 'linux2' else 'data\\'
    filename__ = filename_ + input_filename  # remember it is in a /data subdir
    with open(filename__, 'rb') as source_csvfile:
        reposReader = UnicodeReader(f=source_csvfile, dialect=RepoReaderDialect)
        reposReader.next()
        previous = ''
        for row in reposReader:
            scream.log('Processing row: ' + str(row))
            url = row[1]
            owner = row[0]
            name = row[2]

            key = owner + '/' + name
            scream.log('Key built: ' + key)

            repo = MyRepository()
            repo.setKey(key)
            repo.setInitials(name, owner)
            repo.setUrl(url)

            #check here if repo dont exist already in dictionary!
            if key == previous:
                scream.log('We already found rep ' + key +
                           ' in the dictionary..')
            else:
                repos.put(repo)
                previous = key

    scream.say('Finished creating queue, size of fifo construct is: ' +
               str(repos.qsize()))

    iteration_step_count = 1

    if not os.path.isfile('developers_revealed_from_top.csv'):
        make_headers('developers_revealed_from_top.csv')

    if reverse_queue:
        aux_stack = Stack()
        while not repos.empty():
            aux_stack.push(repos.get())
        while not aux_stack.isEmpty():
            repos.put(aux_stack.pop())

    with open('developers_revealed_from_top.csv', 'ab', 0) as result_file:
        threads = []
        thread_id_count = 0

        result_writer = UnicodeWriter(result_file)
        while not repos.empty():
            repo = repos.get()
            key = repo.getKey()

            # resume on repo is implemented, just provide parameters in argvs
            if resume_on_repo is not None:
                resume_on_repo_owner = resume_on_repo.split('/')[0]
                resume_on_repo_name = resume_on_repo.split('/')[1]
                # here basicly we pass already processed repos
                # hence the continue directive till resume_on_repo pass
                if not ((resume_on_repo_name == repo.getName()) and
                        (resume_on_repo_owner == repo.getOwner())):
                    iteration_step_count += 1
                    continue
                else:
                    resume_on_repo = None
                    iteration_step_count += 1
                    if resume_on_repo_inclusive:
                        scream.say('Not skipping the ' + resume_on_repo)
                    else:
                        scream.say('Starting from the ' + resume_on_repo)
                        continue

            try:
                while True:
                    scream.say('Creating Repository.py instance from API result..')
                    scream.say('Working at the moment on repo: ' + str(repo.getKey()))
                    current_ghc = github_clients[num_modulo(thread_id_count)]
                    current_ghc_desc = github_clients_ids[num_modulo(thread_id_count)]
                    repository = current_ghc.get_repo(repo.getKey())
                    repo.setRepoObject(repository)
                    repo.setStargazersCount(repository.stargazers_count)
                    scream.say('There are ' + str(repo.getStargazersCount()) + ' stargazers.')
                    assert repo.getStargazersCount() is not None
                    repo.setWatchersCount(repository.watchers_count)  # PyGithub must be joking, this works, watchers_count not
                    scream.say('There are ' + str(repo.getWatchersCount()) + ' watchers.')
                    assert repo.getWatchersCount() is not None

                    # from this line move everything to a thread!
                    scream.say('Create instance of GeneralGetter with ID ' + str(thread_id_count) + ' and token ' + str(current_ghc_desc))
                    gg = GeneralGetter(thread_id_count, repository, repo, result_writer, current_ghc)
                    scream.say('Creating instance of GeneralGetter complete')

                    scream.say('Appending thread to collection of threads')
                    threads.append(gg)
                    scream.say('Append complete, threads[] now have size: ' + str(len(threads)))
                    thread_id_count += 1

                    scream.say('Starting thread....')
                    gg.start()
                    break
            except UnknownObjectException as e:
                scream.log_warning('Repo with key + ' + key +
                                   ' not found, error({0}): {1}'.
                                   format(e.status, e.data), True)
                repos_reported_nonexist.write(key + os.linesep)
                continue
            except Exception as e:
                scream.log_warning('Repo with key + ' + key +
                                   ' made other error ({0})'.
                                   format(str(e).decode('utf-8')), True)
                repos_reported_execution_error.write(key + os.linesep)
                freeze(str(e) + ' in MainClass.get_repo(key)')
                scream.say('Trying again with repo ' + str(key))

            iteration_step_count += 1
            scream.ssay('Step no ' + str(iteration_step_count) +
                        '. Ordered working on a repo: ' + key)

            scream.say('threads[] have size: ' + str(len(threads)))
            print threads
            print threads[:]
            print threads[0]
            print type(threads[0])

            while num_working(threads) > no_of_threads:
                time.sleep(0.2)

            scream.say('Inviting new thread to the pool...')

            scream.ssay('Finished processing repo: ' + key + '.. moving on... ')
            result_file.flush()

            #del repos[key]
            'Dictionary cannot change size during iteration'
            'TO DO: associated fields purge so GC will finish the job'
            'implement reset() in intelliRepository.py'
