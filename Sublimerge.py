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

diffView = None


class SublimergeDiffer():
    def difference(self, text1, text2):
        last = None
        data = []

        for line in list(difflib.Differ().compare(text1.splitlines(1), text2.splitlines(1))):
            change = line[0]
            line = line[2:len(line)]

            part = None

            if change == '+':
                part = {'+': line, '-': ''}

            elif change == '-':
                part = {'-': line, '+': ''}

            elif change == ' ':
                part = line

            elif change == '?':
                continue

            if part != None:
                if isinstance(part, str) and isinstance(last, str):
                    data[len(data) - 1] += part
                elif isinstance(part, dict) and isinstance(last, dict):
                    if part['+'] != '':
                        data[len(data) - 1]['+'] += part['+']
                    if part['-'] != '':
                        data[len(data) - 1]['-'] += part['-']
                else:
                    data.append(part)

                last = part

        return data


class SublimergeView():
    left = None
    right = None
    window = None
    currentDiff = -1
    regions = []
    currentRegion = None
    justInitialized = False

    def __init__(self, window, left, right):
        window.run_command('new_window')
        self.window = sublime.active_window()

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

    def loadDiff(self):
        text1 = self.left.substr(sublime.Region(0, self.left.size()))
        text2 = self.right.substr(sublime.Region(0, self.right.size()))

        self.insertDiffContents(SublimergeDiffer().difference(text1, text2))

        self.left.set_read_only(True)
        self.right.set_read_only(True)
        self.window.set_view_index(self.right, 1, 0)

    def enlargeCorrespondingPart(self, part1, part2):
        linesPlus = part1.splitlines()
        linesMinus = part2.splitlines()

        diffLines = len(linesPlus) - len(linesMinus)

        if diffLines < 0:  # linesPlus < linesMinus
            for i in range(-diffLines):
                linesPlus.append('?')

        elif diffLines > 0:  # linesPlus > linesMinus
            for i in range(diffLines):
                linesMinus.append('?')

        result = []

        result.append("\n".join(linesPlus) + "\n")
        result.append("\n".join(linesMinus) + "\n")

        return result

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
                pair = {
                    'regionLeft': None,
                    'regionRight': None,
                    'name': 'diff' + str(i),
                    'mergeLeft': part['+'][:],
                    'mergeRight': part['-'][:]
                }

                i += 1

                #if len(part['+']) > 0:
                edit = left.begin_edit()
                start = left.size()

                enlarged = self.enlargeCorrespondingPart(part['+'], part['-'])

                left.insert(edit, start, enlarged[1])
                length = len(enlarged[1])
                left.end_edit(edit)

                pair['regionLeft'] = sublime.Region(start, start + length)

                edit = right.begin_edit()
                start = right.size()
                right.insert(edit, start, enlarged[0])
                right.end_edit(edit)

                pair['regionRight'] = sublime.Region(start, start + len(enlarged[0]))

                if pair['regionLeft'] != None and pair['regionRight'] != None:
                    regions.append(pair)

        for pair in regions:
            self.createDiffRegion(pair)

        self.regions = regions
        sublime.set_timeout(lambda: self.selectDiff(0), 100)  # for some reason this fixes the problem to scroll both views to proper position after loading diff

    def createDiffRegion(self, region):
        self.left.add_regions(region['name'], [region['regionLeft']], 'selection', 'dot', sublime.DRAW_OUTLINED)
        self.right.add_regions(region['name'], [region['regionRight']], 'selection', 'dot', sublime.DRAW_OUTLINED)

    def createSelectedRegion(self, region):
        self.left.add_regions(region['name'], [region['regionLeft']], 'selection', 'dot')
        self.right.add_regions(region['name'], [region['regionRight']], 'selection', 'dot')

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

            if self.justInitialized:
                self.left.show_at_center(sublime.Region(self.currentRegion['regionLeft'].begin(), self.currentRegion['regionLeft'].begin()))
                self.right.show_at_center(sublime.Region(self.currentRegion['regionRight'].begin(), self.currentRegion['regionRight'].begin()))

            self.justInitialized = True

    def goUp(self):
        self.selectDiff(self.currentDiff - 1)

    def goDown(self):
        self.selectDiff(self.currentDiff + 1)

    def merge(self, direction):
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

            target.set_scratch(False)

            del self.regions[self.currentDiff]

            for i in range(self.currentDiff, len(self.regions)):
                movedRegion = sublime.Region(self.regions[i]['regionLeft'].begin() + diffLenLeft, self.regions[i]['regionLeft'].end() + diffLenLeft)
                self.regions[i]['regionLeft'] = movedRegion

                movedRegion = sublime.Region(self.regions[i]['regionRight'].begin() + diffLenRight, self.regions[i]['regionRight'].end() + diffLenRight)
                self.regions[i]['regionRight'] = movedRegion

                if i != self.currentDiff:
                    self.createDiffRegion(self.regions[i])

            target.set_read_only(True)
            source.set_read_only(True)

            if self.currentDiff > len(self.regions) - 1:
                self.currentDiff = len(self.regions) - 1

            if self.currentDiff >= 0:
                self.currentRegion = self.regions[self.currentDiff]
                self.createSelectedRegion(self.currentRegion)

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

    def selectRegionUnderCaret(self, view, regionKey):
        sel = view.sel()
        if len(sel) == 0:
            return

        selB = sel[0].b
        selBegin = sel[0].begin()
        selEnd = sel[len(sel) - 1].end()

        if selBegin != selEnd:
            sel.clear()
            sel.add(sublime.Region(selB, selB))

        for i in range(len(self.regions)):
            region = self.regions[i][regionKey]
            if region.begin() <= sel[0].begin() and region.end() >= sel[0].end():
                self.selectDiff(i)
                break


class SublimergeCommand(sublime_plugin.WindowCommand):
    viewsList = []
    diffIndex = 0

    def run(self):
        self.viewsList = []
        self.diffIndex = 0
        active = self.window.active_view()
        allViews = self.window.views()

        for view in allViews:
            if view.file_name() != active.file_name():
                self.viewsList.append(view.file_name())

        if self.saved(active):
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
                    diffView = SublimergeView(self.window, self.window.active_view(), compareTo)


class SublimergeGoUpCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goUp()


class SublimergeGoDownCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.goDown()


class SublimergeMergeLeftCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.merge('<<')


class SublimergeMergeRightCommand(sublime_plugin.WindowCommand):
    def run(self):
        if diffView != None:
            diffView.merge('>>')


class SublimergeListener(sublime_plugin.EventListener):
    left = None
    right = None

    def on_selection_modified(self, view):
        global diffView

        if diffView != None:
            if view.id() == diffView.left.id():
                diffView.selectRegionUnderCaret(diffView.left, 'regionLeft')
            elif view.id() == diffView.right.id():
                diffView.selectRegionUnderCaret(diffView.right, 'regionRight')

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
