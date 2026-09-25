import "./index.css";
import { Composition, Folder } from "remotion";
import { SCENE_COMPONENTS, WesternCiv } from "./westernciv/WesternCiv";
import { FPS, SCENES, TOTAL_FRAMES } from "./westernciv/timeline";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="WesternCiv"
        component={WesternCiv}
        durationInFrames={TOTAL_FRAMES}
        fps={FPS}
        width={1920}
        height={1080}
      />
      {/* Each scene on its own, for previewing / rendering stills in isolation */}
      <Folder name="WesternCiv-Scenes">
        {SCENES.map((s) => (
          <Composition
            key={s.id}
            id={`WesternCiv-${s.id}`}
            component={SCENE_COMPONENTS[s.id]}
            durationInFrames={s.frames}
            fps={FPS}
            width={1920}
            height={1080}
          />
        ))}
      </Folder>
    </>
  );
};
