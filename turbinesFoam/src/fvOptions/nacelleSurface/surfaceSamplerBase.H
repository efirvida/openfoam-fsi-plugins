/*---------------------------------------------------------------------------*\
  =========                 |
  \\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox
   \\    /   O peration     |
    \\  /    A nd           | Copyright held by original author(s)
     \\/     M anipulation  |
-------------------------------------------------------------------------------
License
    This file is part of turbinesFoam, which is based on OpenFOAM.

    OpenFOAM is free software: you can redistribute it and/or modify it
    under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    OpenFOAM is distributed in the hope that it will be useful, but WITHOUT
    ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
    FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License
    for more details.

    You should have received a copy of the GNU General Public License
    along with OpenFOAM.  If not, see <http://www.gnu.org/licenses/>.

Class
    Foam::fv::surfaceSamplerBase

Description
    Frame- and force-model-agnostic base for surface-sampling objects.

    It provides only the generic sampling assets shared by the surface
    implementations:

    - the \c MeshedSurface<face> load (format auto-detected from the file
      extension: STL, OBJ, VTK, ...) with case-relative path resolution (key
      configurable, default \c geometry); mixed tri/quad/poly faces are kept
    - the surface vertices (the FSI point cloud) and the centroid node set:
      one node per face in surface face order, with the outward unit normal
      and the area weight
    - the body-frame transform (optional \c bodyOrigin and \c bodyAxis entries,
      completed deterministically) and the body-frame node geometry
    - the local cell size (findCell + reduce(minOp) sentinel)
    - the paper's smoothed four-point cosine kernel (Eq. 8, support |r| <= 2.5)
      and the kernel-smoothed velocity interpolation (Eq. 7)
    - the Eq. 18 distribution helper: candidate list optional, \c nullptr means
      "all local cells" (the original nacelle behavior, byte-for-byte)
    - the reference density \c rhoRef_ for the SI-newton contract conversion

    Concrete samplers add their own force model, body frame and per-node force
    lists (\c nacelleSurfaceSampler is the static-frame, direct-forcing/friction
    consumer; the blade surface sampler is the rotating-frame, BEM-distribution
    consumer). This class never calls a force model.

SourceFiles
    surfaceSamplerBase.C
    surfaceSamplerBaseI.H

\*---------------------------------------------------------------------------*/

#ifndef surfaceSamplerBase_H
#define surfaceSamplerBase_H

#include "autoPtr.H"
#include "List.H"
#include "dictionary.H"
#include "point.H"
#include "vector.H"
#include "tensor.H"
#include "MeshedSurface.H"
#include "face.H"
#include "vectorIOField.H"
#include "Time.H"
#include "fvMesh.H"
#include "volFieldsFwd.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

namespace Foam
{
namespace fv
{

/*---------------------------------------------------------------------------*\
                   Class surfaceSamplerBase Declaration
\*---------------------------------------------------------------------------*/

class surfaceSamplerBase
{

protected:

    // Protected data

        //- Mesh the surface is sampled on
        const fvMesh& mesh_;

        //- Surface mesh (tri/quad/poly), format auto-detected from extension
        autoPtr<MeshedSurface<face>> surface_;

        //- Node positions (global frame, face centroids, face order)
        List<point> positions_;

        //- Node outward unit normals (global frame)
        List<vector> normals_;

        //- Node area weights
        List<scalar> areas_;

        //- Node positions in the body frame (the sampling contract)
        List<point> positionsBody_;

        //- Node normals in the body frame (the sampling contract)
        List<vector> normalsBody_;

        //- Body origin in the global frame
        vector bodyOrigin_;

        //- Body-to-global rotation tensor (columns: body axes in global frame)
        tensor bodyToGlobal_;

        //- Body-to-global transform is identity
        bool identityBodyFrame_;

        //- Reference density for the SI-newton conversion of forces()
        scalar rhoRef_;

        //- Optional FSI coupling layer, enabled by the 'fsi' sub-dictionary
        bool fsiActive_;

        //- FSI registry field names (surface vertices, forces, displacements)
        word fsiCoordFieldName_;
        word fsiForceFieldName_;
        word fsiDispFieldName_;

        //- Owning FSI registry fields; created only when the layer is active
        autoPtr<vectorIOField> fsiCoordFieldPtr_;
        autoPtr<vectorIOField> fsiForceFieldPtr_;
        autoPtr<vectorIOField> fsiDispFieldPtr_;

        //- FSI geometry reference (post-setup vertices and face centroids)
        List<point> fsiReferencePoints_;
        List<point> fsiReferenceCentroids_;

        //- Accumulated rigid rotation of the FSI reference
        point fsiRotationPoint_;
        vector fsiRotationAxis_;
        scalar fsiTotalAngle_;

        //- True once the FSI geometry reference has been captured
        bool fsiGeometryInitialized_;


    // Protected Member Functions

        //- No copy construct
        surfaceSamplerBase(const surfaceSamplerBase&) = delete;

        //- No copy assignment
        void operator=(const surfaceSamplerBase&) = delete;

        //- Build the body frame transform and the body-frame node geometry
        void createBodyFrame(const dictionary& dict);

        //- Local cell size h = cbrt(V[cell]) of the cell containing X,
        //  resolved with a findCell + reduce(minOp) sentinel. Fatal if the
        //  point is not found on any processor (unreachable sample).
        scalar cellSize(const point& X) const;

        //- Smoothed four-point cosine kernel (Eq. 8), support |r| <= 2.5
        static scalar kernel(const scalar r);

        //- Kernel-smoothed velocity interpolation at X (Eq. 7); h is the
        //  node's local cell size
        vector interpolateVelocity
        (
            const point& X,
            const volVectorField& U,
            const scalar h
        ) const;

        //- Refresh the body-frame positions/normals from the global lists
        void updateBodyFrame();

        //- Create the optional FSI registry fields from the 'fsi' sub-dict;
        //  no-op when the sub-dict is absent (the coupling layer stays off)
        void createFsiFields(const dictionary& dict);

        //- Rotation tensor about a unit axis by radians (same arithmetic as
        //  the element rotation, for lockstep)
        static tensor rotationTensor(const vector& axis, const scalar radians);

        //- Distribute the per-node forces onto the local cells (Eq. 18).
        //  When \c candidates is \c nullptr every local cell is visited (the
        //  original nacelle loop); otherwise only the precomputed candidate
        //  cell labels of each node are visited.
        void distributeForce
        (
            volVectorField& ff,
            const List<vector>& nodeForcesGlobal,
            const List<scalar>& nodeH,
            const List<List<label>>* candidates
        ) const;


public:

    // Constructors

        //- Construct from a dictionary and the mesh; \c geometryKey names the
        //  entry giving the surface triangulation file
        surfaceSamplerBase
        (
            const dictionary& dict,
            const fvMesh& mesh,
            const word& geometryKey = "geometry"
        );


    //- Destructor
    virtual ~surfaceSamplerBase();


    // Member Functions

        // Access

            //- Number of nodes (face centroids)
            inline label nNodes() const;

            //- Surface mesh vertices in the global frame (the FSI point cloud)
            inline const pointField& surfacePoints() const;

            //- Node positions in the body frame
            inline const List<point>& positions() const;

            //- Node outward unit normals in the body frame
            inline const List<vector>& normals() const;

            //- Node area weights
            inline const List<scalar>& areas() const;

            //- Node positions in the global (mesh) frame
            inline const List<point>& positionsGlobal() const;

            //- Node outward unit normals in the global (mesh) frame
            inline const List<vector>& normalsGlobal() const;

            //- Body-to-global rotation tensor (columns: body axes in the
            //  global frame); its transpose maps global vectors into the
            //  body frame
            inline const tensor& bodyToGlobal() const;

            //- Reference density used for the SI conversion
            inline scalar rhoRef() const;

            //- True when the optional FSI coupling fields are active
            inline bool fsiActive() const;

            //- True once the FSI geometry reference has been captured
            inline bool fsiGeometryInitialized() const;

            //- FSI registry field names
            inline const word& fsiCoordinateFieldName() const;
            inline const word& fsiForceFieldName() const;
            inline const word& fsiDisplacementFieldName() const;


    // FSI coupling layer

        //- Write the current surface vertices to the coordinate field
        void writeCoordinateField();

        //- Project per-face forces onto the surface vertices (equal split,
        //  force-conserving) and write the FSI force field (global frame).
        //  No-op when the FSI layer is off.
        void writeForceField(const List<vector>& faceForces);

        //- Capture the FSI geometry reference at the post-setup configuration
        //  and reset the accumulated rotation. No-op when the layer is off.
        void initializeFsiGeometry();

        //- Accumulate a rigid rotation of the FSI reference; called from the
        //  sampler's rotate path once the reference is captured
        void accumulateFsiRotation
        (
            const point& rotationPoint,
            const vector& axis,
            const scalar radians
        );

        //- Recompute the current geometry as R(total)*(reference + u_fsi) and
        //  refresh the face centroids, normals and areas. No-op when the layer
        //  is off or the reference is not captured yet.
        void fsiUpdateGeometry();
};


// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

} // End namespace fv
} // End namespace Foam

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#include "surfaceSamplerBaseI.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //

#endif

// ************************************************************************* //
