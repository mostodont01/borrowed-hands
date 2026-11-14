import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtWebEngine

ApplicationWindow {
	id: root
	width: 1400
	height: 900
	visible: true
	title: (web.title ? web.title + " — " : "") + "Borrowed Hands"
	color: "#101722"

	readonly property color panelColor: "#20252c"
	readonly property color cardColor: "#2a2f37"
	readonly property color textColor: "#e3e7ed"
	readonly property color mutedColor: "#929ba8"
	readonly property color accentColor: "#72a7ff"
	readonly property color warnColor: "#fbbf24"

	onClosing: backend.windowClosing()

	WebEngineProfilePrototype {
		id: profileProto
		storageName: "borrowed-hands"
		persistentStoragePath: profilePath
	}

	Connections {
		target: backend
		function onNavigateRequested(url) { web.url = url }
		function onRunJs(requestId, script) {
			web.runJavaScript(script, function (result) {
				backend.jsResult(requestId, JSON.stringify(result === undefined ? null : result))
			})
		}
	}

	RowLayout {
		anchors.fill: parent
		spacing: 0

		// ---- browser -------------------------------------------------------------------
		ColumnLayout {
			Layout.fillWidth: true
			Layout.fillHeight: true
			spacing: 0

			Rectangle {
				Layout.fillWidth: true
				Layout.preferredHeight: 40
				color: root.panelColor

				RowLayout {
					anchors.fill: parent
					anchors.margins: 6
					spacing: 4
					VButton { text: "◀"; subtle: true; enabled: web.canGoBack; onClicked: web.goBack() }
					VButton { text: "▶"; subtle: true; enabled: web.canGoForward; onClicked: web.goForward() }
					VButton { text: web.loading ? "✕" : "⟳"; subtle: true; onClicked: web.loading ? web.stop() : web.reload() }
					TextField {
						id: address
						Layout.fillWidth: true
						implicitHeight: 28
						color: root.textColor
						font.pixelSize: 12
						selectByMouse: true
						background: Rectangle { radius: 5; color: "#262b33"; border.color: address.activeFocus ? root.accentColor : "#383d46" }
						onAccepted: { web.url = text.indexOf("://") < 0 ? "https://" + text : text; web.forceActiveFocus() }
					}
				}
				Rectangle {
					anchors.left: parent.left
					anchors.bottom: parent.bottom
					height: 2
					width: parent.width * web.loadProgress / 100
					color: root.accentColor
					visible: web.loading
				}
			}

			WebEngineView {
				id: web
				Layout.fillWidth: true
				Layout.fillHeight: true
				profile: profileProto.instance()
				url: startUrl

				Component.onCompleted: {
					// The default user agent says "QtWebEngine", which some sites block.
					profile.httpUserAgent = profile.httpUserAgent.replace(/QtWebEngine\/\S+\s*/, "")
				}
				onLoadingChanged: function (info) {
					if (info.status === WebEngineView.LoadStartedStatus)
						backend.pageLoading()
					else if (info.status === WebEngineView.LoadSucceededStatus)
						backend.pageLoaded(web.url.toString(), web.title)
					else
						backend.pageLoadFailed()
				}
				onUrlChanged: { address.text = web.url.toString(); backend.pageChanged(web.url.toString(), web.title) }
				onTitleChanged: backend.pageChanged(web.url.toString(), web.title)
				onNewWindowRequested: function (request) { web.url = request.requestedUrl }
			}
		}

		// ---- Claude's panel ------------------------------------------------------------
		Rectangle {
			Layout.preferredWidth: 360
			Layout.fillHeight: true
			color: root.panelColor

			ColumnLayout {
				anchors.fill: parent
				anchors.margins: 14
				spacing: 12

				Label {
					text: "Claude says"
					color: root.mutedColor
					font.pixelSize: 11
					font.capitalization: Font.AllUppercase
					font.letterSpacing: 1
				}

				Rectangle {
					Layout.fillWidth: true
					implicitHeight: instructionText.implicitHeight + 28
					radius: 8
					color: root.cardColor
					border.color: backend.instruction ? root.accentColor : "#383d46"

					TextEdit {
						id: instructionText
						objectName: "instructionText"
						anchors.fill: parent
						anchors.margins: 14
						anchors.rightMargin: 40
						text: backend.instruction || "Waiting for Claude…"
						color: backend.instruction ? root.textColor : root.mutedColor
						font.pixelSize: 17
						wrapMode: TextEdit.Wrap
						textFormat: TextEdit.PlainText
						readOnly: true
						selectByMouse: true
						selectionColor: "#3b6fd4"
						selectedTextColor: "#ffffff"
					}
					VButton {
						objectName: "copyButton"
						anchors.top: parent.top
						anchors.right: parent.right
						anchors.margins: 6
						text: copied.running ? "✓" : "⧉"
						subtle: true
						visible: backend.instruction !== ""
						ToolTip.visible: hovered
						ToolTip.text: "Copy"
						onClicked: {
							instructionText.selectAll()
							instructionText.copy()
							instructionText.deselect()
							copied.restart()
						}
						Timer { id: copied; interval: 1200 }
					}
				}

				RowLayout {
					Layout.fillWidth: true
					spacing: 8
					VButton {
						Layout.fillWidth: true
						text: "Done"
						kind: "primary"
						implicitHeight: 34
						font.pixelSize: 13
						enabled: backend.instruction !== ""
						onClicked: backend.done()
					}
					VButton {
						text: "Can't do it"
						implicitHeight: 34
						enabled: backend.instruction !== ""
						onClicked: backend.cant()
					}
				}

				RowLayout {
					Layout.fillWidth: true
					spacing: 6
					TextField {
						id: replyField
						Layout.fillWidth: true
						implicitHeight: 30
						placeholderText: "Reply to Claude…"
						placeholderTextColor: root.mutedColor
						color: root.textColor
						font.pixelSize: 12
						background: Rectangle { radius: 5; color: "#262b33"; border.color: replyField.activeFocus ? root.accentColor : "#383d46" }
						onAccepted: send()
						function send() { backend.reply(text); text = "" }
					}
					VButton { text: "Send"; implicitHeight: 30; enabled: replyField.text.trim() !== ""; onClicked: replyField.send() }
				}

				Label {
					text: "History"
					color: root.mutedColor
					font.pixelSize: 11
					font.capitalization: Font.AllUppercase
					font.letterSpacing: 1
					Layout.topMargin: 6
				}

				ListView {
					id: historyList
					Layout.fillWidth: true
					Layout.fillHeight: true
					clip: true
					spacing: 6
					model: backend.history
					onCountChanged: positionViewAtEnd()
					delegate: TextEdit {
						required property var modelData
						width: historyList.width
						wrapMode: TextEdit.Wrap
						font.pixelSize: 12
						textFormat: TextEdit.PlainText
						readOnly: true
						selectByMouse: true
						selectionColor: "#3b6fd4"
						selectedTextColor: "#ffffff"
						color: modelData.who === "claude" ? root.textColor : root.accentColor
						text: (modelData.who === "claude" ? "Claude: " : "You: ") + modelData.text
					}
				}
			}
		}
	}

	// ---- inactivity popup ----------------------------------------------------------------
	Popup {
		id: timeoutPopup
		objectName: "timeoutPopup"
		visible: backend.promptVisible
		modal: true
		closePolicy: Popup.NoAutoClose
		anchors.centerIn: Overlay.overlay
		width: 420
		padding: 22
		background: Rectangle { radius: 10; color: root.panelColor; border.color: root.warnColor; border.width: 2 }

		ColumnLayout {
			anchors.fill: parent
			spacing: 14
			Text { text: "Timeout"; color: root.warnColor; font.pixelSize: 18; font.bold: true }
			Text {
				Layout.fillWidth: true
				wrapMode: Text.Wrap
				color: root.textColor
				font.pixelSize: 14
				text: "Nothing happened for 2 minutes. Continue the search?\nThe window closes in " + backend.secondsLeft + " s."
			}
			RowLayout {
				Layout.alignment: Qt.AlignRight
				spacing: 8
				VButton { text: "No, close"; implicitHeight: 32; onClicked: backend.answerPrompt(false) }
				VButton { text: "Yes, continue"; kind: "primary"; implicitHeight: 32; onClicked: backend.answerPrompt(true) }
			}
		}
	}
}
