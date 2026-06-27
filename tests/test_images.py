from classmarker_crawler.images import collect_image_urls, local_name, update_local_paths


def test_collect_and_update_image_paths():
    url = "https://0cm.classmarker.com/account/image%201.png"
    data = [
        {
            "questions": [
                {
                    "images": [url],
                    "html": f'<img src="{url}">',
                    "answers": [],
                    "answer_given": None,
                    "accepted_answers": [],
                }
            ]
        }
    ]
    assert collect_image_urls(data) == [url]
    assert local_name(url) == "image 1.png"

    update_local_paths(data, {url: "images/image 1.png"})
    question = data[0]["questions"][0]
    assert question["source_images"] == [url]
    assert question["images"] == ["images/image 1.png"]
    assert 'src="images/image 1.png"' in question["html"]
