 # Copyright (c) 2012 Borys Forytarz <borys.forytarz@gmail.com>
 #
 # Permission is hereby granted, free of charge, to any person
 # obtaining a copy of this software and associated documentation files
 # (the "Software"), to deal in the Software without restriction,
 # including without limitation the rights to use, copy, modify,
 # merge, publish, distribute, sublicense, and/or sell copies of the
 # Software, and to permit persons to whom the Software is furnished
 # to do so, subject to the following conditions:
 #
 # The above copyright notice and this permission notice shall be
 # included in all copies or substantial portions of the Software.
 #
 # THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 # EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
 # MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 # NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS
 # BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
 # ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
 # CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
 # SOFTWARE.
 #
 # https://github.com/borysf/Sublimerge


import sublime
import sublime_plugin
import difflib
import re

diffView = None

settings = sublime.load_settings('Sublimerge.sublime-settings')


class SublimergeSettings():
    s = {
        'same_syntax_only': True,
        'hide_side_bar': True,
        'diff_region_expander_text': '?',
        'diff_region_scope': 'selection',
        'diff_region_added_scope': 'markup.inserted',
        'diff_region_removed_scope': 'markup.deleted',
        'diff_region_gutter_icon': 'none',
        'diff_region_change_scope': 'markup.changed',
        'selected_diff_region_scope': 'selection',
        'selected_diff_region_gutter_icon': 'bookmark',
        'ignore_whitespace': False
    }

    def load(self):
        for name in self.s:
            self.s[name] = settings.get(name, self.s[name])

    def get(self, name):
        return self.s[name]

S = SublimergeSettings()
S.load()
settings.add_on_change('reload', lambda: S.load())


class SublimergeDiffer():
    def difference(self, text1, text2):
        data = []
        lines = list(difflib.Differ().compare(text1.splitlines(1), text2.splitlines(1)))

        for i in range(len(lines)):
            line = lines[i]
            lastIdx = len(data) - 1
            change = line[0]
            line = line[2:len(line)]

            part = None

            if change == '+':
                part = {'+': line, '-': '', 'change': '+', 'intraline': '', 'intralines': {'+': [], '-': []}}

            elif change == '-':
                part = {'-': line, '+': '', 'change': '-', 'intraline': '', 'intralines': {'+': [], '-': []}}

            elif change == ' ':
                part = line

            elif change == '?':
                continue

            if isinstance(part, str) and isinstance(data[lastIdx], str):
                data[lastIdx] += part
            else:
                if isinstance(part, dict):
                    if i < len(lines) - 1 and lines[i + 1][0] == '?':
                        part['intraline'] = change

                    if lastIdx >= 0 and isinstance(data[lastIdx], dict):
                        test = (data[lastIdx]['intraline'] == '-' and change == '+') or (data[lastIdx]['intraline'] == '+' and change == '-')
                        test2 = (data[lastIdx]['intraline'] == '+' and part['intraline'] == '-') or (data[lastIdx]['intraline'] == '-' and part['intraline'] == '+')
                        if test or test2 or (data[lastIdx]['intraline'] == '' and part['intraline'] == ''):
                            data[lastIdx]['-'] += part['-']
                            data[lastIdx]['+'] += part['+']
                            if test:
                                data[lastIdx]['intraline'] = '?'
                        else:
                            if (part['+'] != '' and data[lastIdx]['+'] == '') and (part['-'] == '' and data[lastIdx]['-'] != ''):
                                data[lastIdx]['+'] += part['+']
                                data[lastIdx]['intraline'] = '?'
                            elif (part['-'] != '' and data[lastIdx]['-'] == '') and (part['+'] == '' and data[lastIdx]['+'] != ''):
                                data[lastIdx]['-'] += part['-']
                                data[lastIdx]['intraline'] = '?'
                            else:
                                data.append(part)
                    else:
                        data.append(part)
                else:
                    data.append(part)

        return data


class SublimergeScrollSync():
    left = None
    right = None
    scrollingView = None
    viewToSync = None
    lastPosLeft = None
    lastPosRight = None
    isRunning = False
    last = None
    targetPos = None

    def __init__(self, left, right):
        self.left = left
        self.right = right
        self.sync()

    def sync(self):
        beginLeft = self.left.viewport_position()
        beginRight = self.right.viewport_position()

        if not self.isRunning:
            if beginLeft[0] != beginRight[0] or beginLeft[1] != beginRight[1]:
                if self.lastPosLeft == None or (self.lastPosLeft[0] != beginLeft[0] or self.lastPosLeft[1] != beginLeft[1]):
                    self.isRunning = True
                    self.scrollingView = self.left
                    self.viewToSync = self.right

                elif self.lastPosRight == None or (self.lastPosRight[0] != beginRight[0] or self.lastPosRight[1] != beginRight[1]):
                    self.isRunning = True
                    self.scrollingView = self.right
                    self.viewToSync = self.left

        else:
            pos = self.scrollingView.viewport_position()

            if self.targetPos == None and self.last != None and pos[0] == self.last[0] and pos[1] == self.last[1]:
                ve = self.viewToSync.viewport_extent()
                le = self.viewToSync.layout_extent()

                self.targetPos = (max(0, min(pos[0], le[0] - ve[0])), max(0, min(pos[1], le[1] - ve[1])))
                self.viewToSync.set_viewport_position(self.targetPos)

            elif self.targetPos != None:
                poss = self.viewToSync.viewport_position()

                if poss[0] == self.targetPos[0] and poss[1] == self.targetPos[1]:
                    self.isRunning = False
                    self.targetPos = None
                    self.scrollingView = None
                    self.viewToSync = None

            self.last = pos

        self.lastPosRight = beginRight
        self.lastPosLeft = beginLeft

        if self.left.window() != None and self.right.window() != None:
            sublime.set_timeout(self.sync, 100)


class SublimergeView():
    left = None
    right = None
    window = None
    currentDiff = -1
    regions = []
    currentRegion = None
    scrollSyncRunning = False
    lastLeftPos = None
    lastRightPos = None
    diff = None
    createdPositions = False

    def __init__(self, window, left, right, diff):
        window.run_command('new_window')
        self.window = sublime.active_window()
        self.diff = diff

        if (S.get('hide_side_bar')):
            self.window.run_command('toggle_side_bar')

        self.window.set_layout({
            "cols": [0.0, 0.5, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
        })

        self.left = self.window.open_file(left.file_name())
        self.right = self.window.open_file(right.file_name())

        self.left.set_syntax_file(left.settings().get('syntax'))
        self.right.set_syntax_file(right.settings().get('syntax'))
        self.left.set_scratch(True)
        self.right.set_scratch(True)

    def enlargeCorrespondingPart(self, part1, part2):
        linesPlus = part1.splitlines()
        linesMinus = part2.splitlines()

        diffLines = len(linesPlus) - len(linesMinus)

        if diffLines < 0:  # linesPlus < linesMinus
            for i in range(-diffLines):
                linesPlus.append(S.get('diff_region_expander_text'))

        elif diffLines > 0:  # linesPlus > linesMinus
            for i in range(diffLines):
                linesMinus.append(S.get('diff_region_expander_text'))

        result = []

        result.append("\n".join(linesPlus) + "\n")
        result.append("\n".join(linesMinus) + "\n")

        return result

    def loadDiff(self):
        self.window.set_view_index(self.right, 1, 0)
        sublime.set_timeout(lambda: self.insertDiffContents(self.diff), 5)

    def insertDiffContents(self, diff):
        left = self.left
        right = self.right

        edit = left.begin_edit()
        left.erase(edit, sublime.Region(0, left.size()))
        left.end_edit(edit)

        edit = right.begin_edit()
        right.erase(edit, sublime.Region(0, right.size()))
        right.end_edit(edit)

        regions = []
        i = 0

        for part in diff:
            if not isinstance(part, dict):
                edit = left.begin_edit()
                left.insert(edit, left.size(), part)
                left.end_edit(edit)

                edit = right.begin_edit()
                right.insert(edit, right.size(), part)
                right.end_edit(edit)
            else:
                if S.get('ignore_whitespace'):
                    trimRe = '(^\s+)|(\s+$)'
                    if re.sub(trimRe, '', part['+']) == re.sub(trimRe, '', part['-']):
                        edit = left.begin_edit()
                        left.insert(edit, left.size(), part['-'])
                        left.end_edit(edit)

                        edit = right.begin_edit()
                        right.insert(edit, right.size(), part['+'])
                        right.end_edit(edit)
                        continue

                pair = {
                    'regionLeft': None,
                    'regionRight': None,
                    'name': 'diff' + str(i),
                    'mergeLeft': part['+'][:],
                    'mergeRight': part['-'][:],
                    'intralines': {'left': [], 'right': []}
                }

                i += 1

                edit = left.begin_edit()
                leftStart = left.size()

                if part['+'] != '' and part['-'] != '':
                    inlines = list(difflib.Differ().compare(part['-'].splitlines(1), part['+'].splitlines(1)))
                    begins = {'+': 0, '-': 0}
                    lastLen = 0
                    lastChange = None

                    for inline in inlines:
                        change = inline[0:1]
                        inline = inline[2:len(inline)]
                        inlineLen = len(inline)

                        if change != '?':
                            begins[change] += inlineLen
                            lastLen = inlineLen
                            lastChange = change
                        else:
                            for m in re.finditer('([+-^]+)', inline):
                                sign = m.group(0)[0:1]

                                if sign == '^':
                                    sign = lastChange

                                part['intralines'][sign].append([begins[sign] - lastLen + m.start(), begins[sign] - lastLen + m.end()])

                enlarged = self.enlargeCorrespondingPart(part['+'], part['-'])

                left.insert(edit, leftStart, enlarged[1])
                left.end_edit(edit)

                edit = right.begin_edit()
                rightStart = right.size()
                right.insert(edit, rightStart, enlarged[0])
                right.end_edit(edit)

                pair['regionLeft'] = sublime.Region(leftStart, leftStart + len(left.substr(sublime.Region(leftStart, left.size()))))
                pair['regionRight'] = sublime.Region(rightStart, rightStart + len(right.substr(sublime.Region(rightStart, right.size()))))

                if pair['regionLeft'] != None and pair['regionRight'] != None:
                    for position in part['intralines']['-']:
                        change = sublime.Region(leftStart + position[0], leftStart + position[1])
                        pair['intralines']['left'].append(change)

                    for position in part['intralines']['+']:
                        change = sublime.Region(rightStart + position[0], rightStart + position[1])
                        pair['intralines']['right'].append(change)

                    regions.append(pair)

        for pair in regions:
            self.createDiffRegion(pair)

        self.createdPositions = True

        self.regions = regions
        sublime.set_timeout(lambda: self.selectDiff(0), 100)  # for some reason this fixes the problem to scroll both views to proper position after loading diff

        self.left.set_read_only(True)
        self.right.set_read_only(True)
        SublimergeScrollSync(self.left, self.right)

    def createDiffRegion(self, region):
        rightScope = leftScope = S.get('diff_region_scope')

        if region['mergeLeft'] == '':
            rightScope = S.get('diff_region_removed_scope')
            leftScope = S.get('diff_region_added_scope')
        elif region['mergeRight'] == '':
            leftScope = S.get('diff_region_removed_scope')
            rightScope = S.get('diff_region_added_scope')

        if not self.createdPositions:
            self.left.add_regions('intralines' + region['name'], region['intralines']['left'], S.get('diff_region_change_scope'))
            self.right.add_regions('intralines' + region['name'], region['intralines']['right'], S.get('diff_region_change_scope'))

        self.left.add_regions(region['name'], [region['regionLeft']], leftScope, S.get('diff_region_gutter_icon'), sublime.DRAW_OUTLINED)
        self.right.add_regions(region['name'], [region['regionRight']], rightScope, S.get('diff_region_gutter_icon'), sublime.DRAW_OUTLINED)

    def createSelectedRegion(self, region):
        self.left.add_regions(region['name'], [region['regionLeft']], S.get('selected_diff_region_scope'), S.get('selected_diff_region_gutter_icon'))
        self.right.add_regions(region['name'], [region['regionRight']], S.get('selected_diff_region_scope'), S.get('selected_diff_region_gutter_icon'))

    def selectDiff(self, diffIndex):
        if diffIndex >= 0 and diffIndex < len(self.regions):
            self.left.sel().clear()
            self.left.sel().add(sublime.Region(0, 0))
            self.right.sel().clear()
            self.right.sel().add(sublime.Region(0, 0))

            if self.currentRegion != None:
                self.createDiffRegion(self.currentRegion)

            self.currentRegion = self.regions[diffIndex]
            self.createSelectedRegion(self.currentRegion)

            self.currentDiff = diffIndex

            self.left.show_at_center(sublime.Region(self.currentRegion['regionLeft'].begin(), self.currentRegion['regionLeft'].begin()))
            if not S.get('ignore_whitespace'):  # @todo: temporary fix for loosing view sync while ignore_whitespace is true
                self.right.show_at_center(sublime.Region(self.currentRegion['regionRight'].begin(), self.currentRegion['regionRight'].begin()))

    def goUp(self):
        self.selectDiff(self.currentDiff - 1)

    def goDown(self):
        self.selectDiff(self.currentDiff + 1)

    def merge(self, direction, mergeAll):
        if mergeAll:
            while len(self.regions) > 0:
                self.merge(direction, False)
            return

        if (self.currentRegion != None):
            lenLeft = self.left.size()
            lenRight = self.right.size()
            if direction == '<<':
                source = self.right
                target = self.left
                sourceRegion = self.currentRegion['regionRight']
                targetRegion = self.currentRegion['regionLeft']
                contents = self.currentRegion['mergeLeft']

            elif direction == '>>':
                source = self.left
                target = self.right
                sourceRegion = self.currentRegion['regionLeft']
                targetRegion = self.currentRegion['regionRight']
                contents = self.currentRegion['mergeRight']

            target.set_scratch(True)

            target.set_read_only(False)
            source.set_read_only(False)

            edit = target.begin_edit()
            target.replace(edit, targetRegion, contents)
            target.end_edit(edit)

            edit = source.begin_edit()
            source.replace(edit, sourceRegion, contents)
            source.end_edit(edit)

            diffLenLeft = self.left.size() - lenLeft
            diffLenRight = self.right.size() - lenRight

            source.erase_regions(self.currentRegion['name'])
            target.erase_regions(self.currentRegion['name'])
            source.erase_regions('intralines' + self.currentRegion['name'])
            target.erase_regions('intralines' + self.currentRegion['name'])

            target.set_scratch(False)

            del self.regions[self.currentDiff]

            for i in range(self.currentDiff, len(self.regions)):
                self.regions[i]['regionLeft'] = self.moveRegionBy(self.regions[i]['regionLeft'], diffLenLeft)
                self.regions[i]['regionRight'] = self.moveRegionBy(self.regions[i]['regionRight'], diffLenRight)

                # for j in range(self.currentDiff, len(self.regions[i]['intralines']['left'])):
                #     self.regions[i]['intralines']['left'][j] = self.moveRegionBy(self.regions[i]['intralines']['left'][j], diffLenLeft)

                # for j in range(self.currentDiff, len(self.regions[i]['intralines']['right'])):
                #     self.regions[i]['intralines']['right'][j] = self.moveRegionBy(self.regions[i]['intralines']['right'][j], diffLenRight)

                if i != self.currentDiff:
                    self.createDiffRegion(self.regions[i])

            target.set_read_only(True)
            source.set_read_only(True)

            if self.currentDiff > len(self.regions) - 1:
                self.currentDiff = len(self.regions) - 1

            self.currentRegion = None

            if self.currentDiff >= 0:
                self.selectDiff(self.currentDiff)
            else:
                self.currentDiff = -1

            self.window.focus_view(target)

    def moveRegionBy(self, region, by):
        return sublime.Region(region.begin() + by, region.end() + by)

    def abandonUnmergedDiffs(self, side):
        if side == 'left':
            view = self.left
            regionKey = 'regionLeft'
            contentKey = 'mergeRight'
        elif side == 'right':
            view = self.right
            regionKey = 'regionRight'
            contentKey = 'mergeLeft'

        view.set_read_only(False)
        edit = view.begin_edit()

        for i in range(len(self.regions)):
            sizeBefore = view.size()
            view.replace(edit, self.regions[i][regionKey], self.regions[i][contentKey])
            sizeDiff = view.size() - sizeBefore

            if sizeDiff != 0:
                for j in range(i, len(self.regions)):
                    self.regions[j][regionKey] = sublime.Region(self.regions[j][regionKey].begin() + sizeDiff, self.regions[j][regionKey].end() + sizeDiff)

        view.end_edit(edit)
        view.set_read_only(True)


class SublimergeDiffThread():
    def __init__(self, window, left, right):
        self.window = window
        self.left = left
        self.right = right
        sublime.set_timeout(self.run, 0)

    def run(self):
        global diffView
        text1 = self.left.substr(sublime.Region(0, self.left.size()))
        text2 = self.right.substr(sublime.Region(0, self.right.size()))

        diff = SublimergeDiffer().difference(text1, text2)

        differs = False

        if S.get('ignore_whitespace'):
            regexp = re.compile('(^\s+)|(\s+$)', re.MULTILINE)
            if re.sub(regexp, '', text1) != re.sub(regexp, '', text2):
                differs = True
        elif text1 != text2:
            differs = True

        if not differs:
            sublime.message_dialog('There is no difference between files')
            return

        diffView = SublimergeView(self.window, self.left, self.right, diff)
        self.left.erase_status('sublimerge-computing-diff')


class SublimergeCommand(sublime_plugin.WindowCommand):
    viewsList = []
    diffIndex = 0

    def run(self):
        self.viewsList = []
        self.diffIndex = 0
        active = self.window.active_view()

        if self.saved(active):
            allViews = self.window.views()

            for view in allViews:
                if view.file_name() != None and view.file_name() != active.file_name() and (not S.get('same_syntax_only') or view.settings().get('syntax') == active.settings().get('syntax')):
                    self.viewsList.append(view.file_name())

            self.window.show_quick_panel(self.viewsList, self.onListSelect)

    def saved(self, view):
        if view.is_dirty():
            sublime.error_message('File `' + view.file_name() + '` must be saved in order to compare')
            return False

        return True

    def onListSelect(self, itemIndex):
        if itemIndex > -1:
            allViews = self.window.views()
            compareTo = None
            for view in allViews:
                if (view.file_name() == self.viewsList[itemIndex]):
                    compareTo = view
                    break

            if compareTo != None:
                global diffView

                if self.saved(compareTo):
                    active = self.window.active_view()
                    active.set_status('sublimerge-computing-diff', 'Computing differences...')
                    SublimergeDiffThread(self.window, active, compareTo)


class SublimergeGoUpCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goUp()


class SublimergeGoDownCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goDown()


class SublimergeMergeLeftCommand(sublime_plugin.WindowCommand):
    def run(self, mergeAll=False):
        if diffView != None:
            diffView.merge('<<', mergeAll)


class SublimergeMergeRightCommand(sublime_plugin.WindowCommand):
    def run(self, mergeAll=False):
        if diffView != None:
            diffView.merge('>>', mergeAll)


class SublimergeListener(sublime_plugin.EventListener):
    left = None
    right = None

    def on_load(self, view):
        global diffView

        if diffView != None:
            if view.id() == diffView.left.id():
                print "Left file: " + view.file_name()
                self.left = view

            elif view.id() == diffView.right.id():
                print "Right file: " + view.file_name()
                self.right = view

            if self.left != None and self.right != None:
                diffView.loadDiff()
                self.left = None
                self.right = None

    def on_pre_save(self, view):
        global diffView

        if (diffView):
            if view.id() == diffView.left.id():
                diffView.abandonUnmergedDiffs('left')

            elif view.id() == diffView.right.id():
                diffView.abandonUnmergedDiffs('right')

    def on_post_save(self, view):
        global diffView

        if diffView and (view.id() == diffView.left.id() or view.id() == diffView.right.id()):
            wnd = view.window()
            if wnd:
                wnd.run_command('close_window')

    def on_close(self, view):
        global diffView

        if diffView != None:
            if view.id() == diffView.left.id():
                wnd = diffView.right.window()
                if wnd != None:
                    wnd.run_command('close_window')
                diffView = None

            elif view.id() == diffView.right.id():
                wnd = diffView.left.window()
                if wnd != None:
                    wnd.run_command('close_window')
                diffView = None
